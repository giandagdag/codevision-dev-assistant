"""Fix G3 step 1: the sandbox starts the tests with DA_CODEVISION_PYTHON when it is set.

No real CodeVision Python is started: the version question and the process start are faked, and a
"CodeVision Python" is only a file in a temp folder."""

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents import da_sandbox, da_sandbox_python
from agents.da_sandbox_python import MISSING_FILE_TEXT, NO_VERSION_TEXT

SRC = Path(__file__).parent.parent / "src"
REFERENCE = Path(__file__).parent / "fixtures" / "da_reference_codevision"
EXCLUDE = [".env", "*.db", ".git"]
TEXT = (
    "import unittest\n\n\nclass C(unittest.TestCase):\n"
    '    def test_t1_ac1_x(self):\n        """X."""\n        self.assertTrue(True)\n'
)


@pytest.fixture
def fake_python(tmp_path):
    path = tmp_path / "python.exe"
    path.write_text("not a real python")
    return str(path)


def settings_with(path=""):
    return SimpleNamespace(codevision_python=path)


def say_version(monkeypatch, text):
    monkeypatch.setattr(da_sandbox_python, "_probe", lambda path, args: text)
    da_sandbox_python._versions.clear()


def capture_start(monkeypatch):
    """Replaces the process start: remembers the command, then refuses to start (ran=False)."""
    seen = []

    def popen(command, **_options):
        seen.append(command)
        raise OSError("fake: not started")

    monkeypatch.setattr(da_sandbox.subprocess, "Popen", popen)
    return seen


def test_g3_2_not_set_uses_this_apps_python():
    found = da_sandbox_python.test_python(settings_with(""))
    assert found.path == sys.executable and found.source == "own" and not found.error
    assert found.where == "Developer Assistant .venv" and sys.executable not in found.label


def test_g3_1_a_set_python_is_used_for_the_run(monkeypatch, fake_python):
    say_version(monkeypatch, "3.14.2\n")
    seen = capture_start(monkeypatch)

    da_sandbox.run_tests(
        REFERENCE, {}, "g3", TEXT, exclude=EXCLUDE, timeout_seconds=5,
        settings=settings_with(fake_python),
    )  # fmt: skip

    assert seen and seen[0][0] == fake_python
    found = da_sandbox_python.test_python(settings_with(fake_python))
    assert found.label == "CodeVision's Python 3.14.2" and fake_python not in found.label
    assert found.where == "CodeVision .venv"


def test_g3_1_the_safety_net_runner_uses_it_too(monkeypatch, fake_python):
    from agents.da_safety_net_flow import sandbox_runner

    say_version(monkeypatch, "3.14.0\n")
    seen = capture_start(monkeypatch)
    settings = SimpleNamespace(
        codevision_python=fake_python, sandbox_source_dir=REFERENCE, llm_provider="fake"
    )
    policy = SimpleNamespace(build_sandbox_exclude=EXCLUDE, build_test_timeout_seconds=5)

    sandbox_runner(settings, "CVDA-2026-0001", policy)(TEXT, {})

    assert seen[0][0] == fake_python


def test_g3_1_every_run_tests_call_in_src_passes_settings():
    """Six calls today (four in the build loop, refine bug, safety net). A new one that forgets
    `settings=` would quietly use the wrong Python: the bug this fix removes."""
    missing, count = [], 0
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "run_tests":
                count += 1
                if "settings" not in {k.arg for k in node.keywords}:
                    missing.append(f"{path.name}:{node.lineno}")
    assert count == 6 and not missing


def test_g3_3_a_missing_file_refuses_the_run_in_plain_words(monkeypatch, tmp_path):
    seen = capture_start(monkeypatch)

    result = da_sandbox.run_tests(
        REFERENCE, {}, "g3", TEXT, exclude=EXCLUDE, timeout_seconds=5,
        settings=settings_with(str(tmp_path / "nope" / "python.exe")),
    )  # fmt: skip

    assert not result.ran and MISSING_FILE_TEXT in result.error
    assert seen == []  # nothing started, so no round was used


def test_g3_4_a_python_older_than_3_14_is_refused_with_its_version(monkeypatch, fake_python):
    say_version(monkeypatch, "3.13.7\n")
    seen = capture_start(monkeypatch)

    result = da_sandbox.run_tests(
        REFERENCE, {}, "g3", TEXT, exclude=EXCLUDE, timeout_seconds=5,
        settings=settings_with(fake_python),
    )  # fmt: skip

    assert not result.ran and "3.13.7" in result.error and seen == []


def test_a_version_call_that_fails_is_refused(monkeypatch, fake_python):
    say_version(monkeypatch, None)
    assert da_sandbox_python.test_python(settings_with(fake_python)).error == NO_VERSION_TEXT
    say_version(monkeypatch, "garbage")
    assert da_sandbox_python.test_python(settings_with(fake_python)).error == NO_VERSION_TEXT


def test_the_version_is_asked_once_per_file(monkeypatch, fake_python):
    calls = []
    monkeypatch.setattr(
        da_sandbox_python, "_probe", lambda path, args: calls.append(path) or "3.14.1"
    )
    da_sandbox_python._versions.clear()
    da_sandbox_python.test_python(settings_with(fake_python))
    da_sandbox_python.test_python(settings_with(fake_python))
    assert len(calls) == 1


def test_missing_libraries_in_process_and_through_the_test_python(monkeypatch, fake_python):
    own = da_sandbox_python.test_python(settings_with(""))
    names = ["json", "no_such_lib_g3"]
    assert da_sandbox_python.missing_libraries(own, names) == {"no_such_lib_g3"}

    say_version(monkeypatch, "3.14.0")
    other = da_sandbox_python.test_python(settings_with(fake_python))
    monkeypatch.setattr(da_sandbox_python, "_probe", lambda path, args: "openpyxl\n")
    assert da_sandbox_python.missing_libraries(other, ["openpyxl", "json"]) == {"openpyxl"}
    monkeypatch.setattr(da_sandbox_python, "_probe", lambda path, args: None)
    assert da_sandbox_python.missing_libraries(other, ["openpyxl"]) == set()  # a failed call


def test_the_runner_and_the_evidence_helper_stay_standard_library_only():
    """They now run in CodeVision's Python, which has none of our libraries."""
    for name in ("da_sandbox_runner.py", "da_evidence_helper.py"):
        tree = ast.parse((SRC / "agents" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            tops = []
            if isinstance(node, ast.Import):
                tops = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                tops = [(node.module or "").split(".")[0]]
            assert all(top in sys.stdlib_module_names for top in tops), (name, tops)
