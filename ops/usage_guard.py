"""Usage guard (A1): answers GO or STOP from the plan's 5-hour and weekly usage.

AS400 comparison: a job checks a data area before every step. The data area is
`ops/state/usage.json`. If the data area cannot be read, the answer is STOP (fails closed).

The usage endpoint is NOT documented by Anthropic, and no URL is guessed here. The URL and the
token file come from settings (`DA_USAGE_URL`, `DA_USAGE_TOKEN_FILE`). Empty means "guard
blind", and blind means STOP. Gian fills them in at A-P1 on the laptop and confirms the reply
shape then. Until then `parse_usage_response` only accepts the status-line style names
(`five_hour.used_percentage`, `seven_day.used_percentage`, `resets_at`); anything else is blind.
"""

import json
import os
import sys
import time
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


def parse_usage_response(body: dict, now: float) -> Usage:
    try:
        five = body["five_hour"]
        week = body["seven_day"]
        return Usage(
            five_hour=float(five["used_percentage"]),
            weekly=float(week["used_percentage"]),
            five_hour_resets_at=_epoch(five.get("resets_at")),
            weekly_resets_at=_epoch(week.get("resets_at")),
            read_at=now,
        )
    except (KeyError, TypeError, ValueError):
        raise GuardBlind("the usage reply has an unexpected shape") from None


def _epoch(value) -> float | None:
    return None if value is None else float(value)


def endpoint_reader() -> Usage:
    """Ask the configured usage endpoint with the laptop's login token. Fails closed."""
    url = os.environ.get("DA_USAGE_URL", "").strip()
    token_file = os.environ.get("DA_USAGE_TOKEN_FILE", "").strip()
    if not url or not token_file:
        raise GuardBlind("DA_USAGE_URL and DA_USAGE_TOKEN_FILE are not set yet (done at A-P1)")
    if not url.startswith("https://"):
        raise GuardBlind("DA_USAGE_URL must start with https://")
    try:
        token = Path(token_file).read_text(encoding="utf-8").strip()
    except OSError:
        raise GuardBlind("the token file could not be read") from None
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as reply:  # noqa: S310 (https only)
            body = json.loads(reply.read().decode("utf-8"))
    except (OSError, ValueError):
        # Never include the exception text: it could echo request details.
        raise GuardBlind("the usage endpoint did not answer") from None
    return parse_usage_response(body, time.time())


def main(reader: Reader = endpoint_reader) -> int:
    decision = decide(get_usage(reader))
    print(("GO: " if decision.go else "STOP: ") + decision.reason)
    return 0 if decision.go else 1


if __name__ == "__main__":
    sys.exit(main())
