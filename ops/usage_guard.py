"""Usage guard (A1): answers GO or STOP from the plan's 5-hour and weekly usage.

AS400 comparison: a job checks a data area before every step. The data area is
`ops/state/usage.json`. If the data area cannot be read, the answer is STOP (fails closed).

Where the numbers come from (Gian's decision D-D option 1, details from 6 Nov): a GET to
https://api.anthropic.com/api/oauth/usage with header `anthropic-beta: oauth-2025-04-20` and the
laptop login token, read (never written) from `~/.claude/.credentials.json`
(`%USERPROFILE%\\.claude\\.credentials.json` on Windows). This is NOT an official public API, so
it can change: anything unexpected means "guard blind", and blind means STOP.
On HTTP 401 the guard runs `claude -p "/usage"` once (which refreshes the login) and retries once.

Two reply shapes are understood (A-P1 confirms them on the laptop):
  A. `{"five_hour": {"used_percentage": 12.5, "resets_at": <epoch seconds>}, "seven_day": {...}}`
     (the shape Claude Code's status line documents)
  B. `{"five_hour": {"utilization": 12.5, "resets_at": "<ISO time>"}, "seven_day": {...}}`
     (`utilization` is a percent from 0 to 100, confirmed by Gian on 6 Nov)
A third layout, a "limits" list, is NOT confirmed and is not supported: it is "guard blind".
Every reply is saved raw to `ops/state/usage_raw.json` so A-P1 can check the real layout.
A value that is missing, not a plain number, or outside 0 to 100 is also "guard blind".
"""

import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

WEEKLY_STOP = 80  # Gian, 6 Nov: stop at 80% of the weekly limit
FIVE_HOUR_STOP = 85  # and at 85% of the 5-hour limit
MAX_AGE_SECONDS = 180  # older than this, the hook re-reads the usage itself (X17)
SGT = timezone(timedelta(hours=8))  # fixed +8, so Windows without tz data still works

ROOT = Path(__file__).resolve().parent.parent


class GuardBlind(Exception):
    """The usage could not be read. The message is safe to show (never holds the token)."""


@dataclass(frozen=True)
class Usage:
    five_hour: float
    weekly: float
    five_hour_resets_at: float | None  # Unix seconds
    weekly_resets_at: float | None
    read_at: float

    def __post_init__(self):
        # Fail closed: NaN, infinity, negative or over-100 numbers must never reach decide(),
        # where every comparison with NaN is False and would read as GO.
        for name in ("five_hour", "weekly"):
            value = getattr(self, name)
            if isinstance(value, bool) or not (math.isfinite(value) and 0 <= value <= 100):
                raise ValueError(f"{name} must be a number from 0 to 100")
        for name in ("five_hour_resets_at", "weekly_resets_at"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if not math.isfinite(self.read_at):
            raise ValueError("read_at must be a finite number")


@dataclass(frozen=True)
class Decision:
    go: bool
    reason: str
    resets_at: float | None = None


Reader = Callable[[], Usage]


def state_path() -> Path:
    return Path(os.environ.get("DA_STATE_DIR", ROOT / "ops" / "state")) / "usage.json"


def format_sgt(epoch: float | None) -> str:
    if epoch is None:
        return "unknown time"
    return datetime.fromtimestamp(epoch, UTC).astimezone(SGT).strftime("%d %b %H:%M SGT")


def decide(usage: Usage | None) -> Decision:
    if usage is None:
        return Decision(False, "guard blind: the usage could not be read")
    if usage.weekly >= WEEKLY_STOP:
        return Decision(
            False,
            f"weekly {usage.weekly:g}%, resets {format_sgt(usage.weekly_resets_at)}",
            usage.weekly_resets_at,
        )
    if usage.five_hour >= FIVE_HOUR_STOP:
        return Decision(
            False,
            f"5-hour {usage.five_hour:g}%, resets {format_sgt(usage.five_hour_resets_at)}",
            usage.five_hour_resets_at,
        )
    return Decision(True, "within the usage lines")


def stopped_line(decision: Decision) -> str:
    """The STATUS.md text for a STOP (AC-1): 'Stopped: weekly 8x%, resets <time SGT>'."""
    return f"Stopped: {decision.reason}"


def write_state(usage: Usage, path: Path | None = None) -> None:
    path = path or state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(usage.__dict__), encoding="utf-8")


def read_state(path: Path | None = None) -> Usage | None:
    try:
        data = json.loads((path or state_path()).read_text(encoding="utf-8"))
        return Usage(**data)
    except (OSError, ValueError, TypeError):
        return None


def get_usage(reader: Reader, now: float | None = None, path: Path | None = None) -> Usage | None:
    """Use the saved state if it is fresh, otherwise re-read. A failed re-read gives None."""
    now = time.time() if now is None else now
    saved = read_state(path)
    if saved is not None and 0 <= now - saved.read_at <= MAX_AGE_SECONDS:
        return saved
    try:
        fresh = reader()
    except GuardBlind:
        return None
    write_state(fresh, path)
    return fresh


DEFAULT_URL = "https://api.anthropic.com/api/oauth/usage"
BETA_HEADER = "oauth-2025-04-20"


class _Unauthorized(Exception):
    """HTTP 401 from the usage endpoint (the login may need a refresh)."""


def _window(body: dict, name: str) -> tuple[float, float | None]:
    """(percent, reset time in epoch seconds) for one window, in either reply shape."""
    window = body[name]
    if "used_percentage" in window:  # shape A
        percent = window["used_percentage"]
    elif "utilization" in window:  # shape B
        percent = window["utilization"]
    else:
        raise KeyError("percentage")
    if isinstance(percent, bool) or not isinstance(percent, int | float):
        raise ValueError("a percentage must be a plain number")  # missing, text, true/false
    return float(percent), _epoch(window.get("resets_at"))


def _epoch(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("not a time")
    if isinstance(value, int | float):
        return float(value)
    return datetime.fromisoformat(str(value)).timestamp()  # ISO time, e.g. 2027-01-15T09:00:00Z


def parse_usage_response(body: dict, now: float) -> Usage:
    try:
        five, five_reset = _window(body, "five_hour")
        week, week_reset = _window(body, "seven_day")
        return Usage(five, week, five_reset, week_reset, now)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise GuardBlind("the usage reply has an unexpected shape") from None


def credentials_path() -> Path:
    override = os.environ.get("DA_CREDENTIALS_FILE", "").strip()
    return Path(override) if override else Path.home() / ".claude" / ".credentials.json"


def read_token() -> str:
    """The login token. The file is opened for reading only, never written."""
    try:
        with credentials_path().open("r", encoding="utf-8") as handle:
            token = json.load(handle)["claudeAiOauth"]["accessToken"]
        if isinstance(token, str) and token.strip():
            return token.strip()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    raise GuardBlind("the Claude login file could not be read (run claude once and log in)")


def _save_raw(raw: str) -> None:
    """Keep the last raw reply in `ops/state/usage_raw.json` (local, Git ignores it), so A-P1 can
    check the real layout. It holds the reply only, never the token. A save problem is ignored."""
    try:
        target = state_path().parent / "usage_raw.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(raw, encoding="utf-8")
    except OSError:
        pass


def _fetch(token: str) -> Usage:
    url = os.environ.get("DA_USAGE_URL", "").strip() or DEFAULT_URL
    if not url.startswith("https://"):
        raise GuardBlind("DA_USAGE_URL must start with https://")
    request = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {token}", "anthropic-beta": BETA_HEADER})
    try:
        with urllib.request.urlopen(request, timeout=15) as reply:  # noqa: S310 (https only)
            raw = reply.read().decode("utf-8")
        _save_raw(raw)
        body = json.loads(raw)
    except urllib.error.HTTPError as problem:
        if problem.code == 401:
            raise _Unauthorized from None
        raise GuardBlind("the usage endpoint did not answer") from None
    except (OSError, ValueError):
        # Never include the exception text: it could echo request details.
        raise GuardBlind("the usage endpoint did not answer") from None
    return parse_usage_response(body, time.time())


def refresh_login() -> None:
    """Run `claude -p "/usage"` once, which refreshes the login. Never nests, never loops."""
    if os.environ.get("DA_USAGE_REFRESHING") == "1":
        raise GuardBlind("already refreshing the login")
    # No DA_WORKER for the child, so its own hooks do nothing (they would call this guard).
    env = {k: v for k, v in os.environ.items() if k != "DA_WORKER"}
    env["DA_USAGE_REFRESHING"] = "1"
    try:
        subprocess.run(["claude", "-p", "/usage"], capture_output=True, text=True, env=env,
                       timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        raise GuardBlind("could not run claude to refresh the login") from None


def endpoint_reader() -> Usage:
    """Ask the usage endpoint with the laptop's login. Fails closed (GuardBlind)."""
    try:
        return _fetch(read_token())
    except _Unauthorized:
        refresh_login()
        try:
            return _fetch(read_token())  # the file may hold a refreshed token now
        except _Unauthorized:
            raise GuardBlind("the login is still refused after a refresh") from None


def main(reader: Reader = endpoint_reader) -> int:
    decision = decide(get_usage(reader))
    print(("GO: " if decision.go else "STOP: ") + decision.reason)
    return 0 if decision.go else 1


if __name__ == "__main__":
    sys.exit(main())
