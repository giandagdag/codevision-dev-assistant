"""Safety net: no test in this folder may start a real `gh` or `claude` (rule: tests never
call the internet). chief_tick's and usage_guard's own `subprocess` are swapped for a stub
that raises."""

import hashlib
import subprocess
from pathlib import Path

import chief_tick
import pytest
import status_board
import usage_guard


class _NoProcesses:
    SubprocessError = subprocess.SubprocessError

    @staticmethod
    def run(*args, **kwargs):
        raise AssertionError(f"a test tried to start a real process: {args[:1]}")


@pytest.fixture(autouse=True)
def _no_real_gh_or_claude(monkeypatch):
    monkeypatch.setattr(chief_tick, "subprocess", _NoProcesses)
    monkeypatch.setattr(usage_guard, "subprocess", _NoProcesses)


@pytest.fixture(autouse=True)
def _board_is_off_and_sandboxed(monkeypatch, tmp_path):
    """Phase A fix 2: the Team status board never runs for real in a test. `main()` calls
    `status_board.refresh`, so it is a no-op here; the board's own tests import the real function
    before this patch and pass fakes. Its log file and subprocess are sandboxed as well."""
    monkeypatch.setattr(status_board, "subprocess", _NoProcesses)
    monkeypatch.setattr(status_board, "refresh", lambda *args, **kwargs: "off")


@pytest.fixture(autouse=True)
def _ops_paths_in_tmp(tmp_path, monkeypatch):
    """Phase A fix 3 (F6): every path the ops code writes to is inside `tmp_path`, so no test can
    leave rows in the real ledger or files in `logs/workers/` (the 8 Nov "15 Jan 16:00" rows came
    from tests that called `tick` or `main` without these set). A test may still set its own."""
    monkeypatch.setenv("DA_LEDGER_FILE", str(tmp_path / "usage-ledger.csv"))
    monkeypatch.setenv("DA_WORKER_LOG_DIR", str(tmp_path / "workers"))
    monkeypatch.setenv("DA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DA_LOG_DIR", str(tmp_path / "quiet"))
    monkeypatch.setenv("DA_STATUS_BOARD_LOG", str(tmp_path / "status_board.log"))
    status = tmp_path / "STATUS.md"
    status.write_text("# STATUS\n\n## Where we are\n- Next: none\n\n## Log\n", encoding="utf-8")
    monkeypatch.setattr(chief_tick, "STATUS_FILE", status)


# ---- the guard (AS-8): the real ledger and worker folder must not change ----

REAL_LOGS = Path(__file__).resolve().parents[2] / "logs"
SNAPSHOT: dict = {}


def snapshot(logs: Path) -> dict:
    """What the ledger file and the worker reply folder look like (names, sizes, content hash)."""
    ledger = logs / "usage-ledger.csv"
    workers = logs / "workers"
    return {
        "ledger": (ledger.stat().st_size, hashlib.sha256(ledger.read_bytes()).hexdigest())
        if ledger.exists() else None,
        "workers": sorted((p.name, p.stat().st_size) for p in workers.iterdir())
        if workers.is_dir() else None,
    }


@pytest.fixture(scope="session", autouse=True)
def _remember_real_logs():
    SNAPSHOT["before"] = snapshot(REAL_LOGS)
    yield
