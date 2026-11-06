"""Safety net: no test in this folder may start a real `gh` or `claude` (rule: tests never
call the internet). chief_tick's own `subprocess` is swapped for a stub that raises."""

import subprocess

import chief_tick
import pytest


class _NoProcesses:
    SubprocessError = subprocess.SubprocessError

    @staticmethod
    def run(*args, **kwargs):
        raise AssertionError(f"a test tried to start a real process: {args[:1]}")


@pytest.fixture(autouse=True)
def _no_real_gh_or_claude(monkeypatch):
    monkeypatch.setattr(chief_tick, "subprocess", _NoProcesses)
