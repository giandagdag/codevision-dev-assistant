"""Safety net: no test in this folder may start a real `gh` or `claude` (rule: tests never
call the internet). chief_tick's and usage_guard's own `subprocess` are swapped for a stub
that raises."""

import subprocess

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
    monkeypatch.setenv("DA_STATUS_BOARD_LOG", str(tmp_path / "status_board.log"))
    monkeypatch.setattr(status_board, "refresh", lambda *args, **kwargs: "off")
