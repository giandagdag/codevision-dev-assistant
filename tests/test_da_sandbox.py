"""Layer B with REAL subprocesses on a made-up CodeVision-shaped folder (rows 6-13 to 6-17, 6-41).

No AI and no internet. Each test sets its own short time limit so the suite stays fast."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agents import da_sandbox
from agents.da_sandbox import run_tests

REFERENCE = Path(__file__).parent / "fixtures" / "da_reference_codevision"
TEST_ID = "cvda_2026_0001"
EXCLUDE = [".env", "*.db", ".git", "*.key", "*.pem"]
MODIFY = "src/agents/upload_validator.py"

PASSING = '''
import unittest
from agents.upload_validator import validate


class Checks(unittest.TestCase):
    def test_t1_ac1_accepts(self):
        """Accepts."""
        self.assertTrue(validate("a"))
'''


def run(test_text=PASSING, code=None, reference=REFERENCE, timeout=20, parent=None):
    return run_tests(
        reference,
        code or {},
        TEST_ID,
        test_text,
        exclude=EXCLUDE,
        timeout_seconds=timeout,
        parent=parent,
    )


IS_WINDOWS = os.name == "nt"  # a name of its own, so a test can pretend (see below)


def run_tasklist(pid: int) -> str:
    """The text Windows' own tasklist prints for one process id (standard library only)."""
    return subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout


def tasklist_says_alive(output: str, pid: int) -> bool:
    """tasklist /NH /FO CSV prints one row like "python.exe","1234","Console",... for a live
    process and an INFO line ("No tasks are running ...") for a missing one."""
    return any(f'"{pid}"' in line for line in output.splitlines())


def is_alive(pid: int) -> bool:
    """Is this process still running? A killed child can stay in the process table as a 'zombie'
    until the container's first process clears it. A zombie is dead, so it does not count.

    On Windows os.kill(pid, 0) must NOT be used: signal 0 is CTRL_C_EVENT there, so it sent Ctrl+C
    to pytest itself (KeyboardInterrupt). tasklist only reads."""
    if IS_WINDOWS:
        return tasklist_says_alive(run_tasklist(pid), pid)
    status = Path(f"/proc/{pid}/status")
    if status.exists():  # Linux
        for line in status.read_text().splitlines():
            if line.startswith("State:"):
                return not line.split()[1].startswith("Z")
        return False
    try:
        os.kill(pid, 0)  # macOS and other Unix: signal 0 only checks that the process exists
    except OSError:
        return False
    return True


def body(*lines):
    """A test file with one test whose body is the given lines."""
    inner = "\n".join("        " + line for line in lines)
    return (
        "import unittest\n\n\nclass Checks(unittest.TestCase):\n"
        '    def test_t1_ac1_x(self):\n        """X."""\n' + inner + "\n"
    )


def test_a_passing_test_is_saved_per_test_and_the_folder_is_deleted(tmp_path):
    """Test 6-13."""
    result = run(parent=tmp_path)

    assert result.ok and result.ran and not result.timed_out
    assert [(t.name, t.result) for t in result.tests] == [("test_t1_ac1_accepts", "pass")]
    assert list(tmp_path.iterdir()) == []  # the temporary folder is gone


def test_the_folder_is_deleted_even_when_the_tests_fail(tmp_path):
    result = run(body("self.fail('nope')"), parent=tmp_path)

    assert not result.ok
    assert list(tmp_path.iterdir()) == []


def test_a_failing_test_keeps_its_message_and_the_end_of_its_traceback():
    result = run(body("self.assertEqual(1, 2, 'one is not two')"))

    only = result.tests[0]
    assert (only.result, result.failed, result.ok) == ("fail", 1, False)
    assert "one is not two" in only.message
    assert 0 < len(only.traceback_tail) <= 20
    assert any("test_cvda_2026_0001.py" in line for line in only.traceback_tail)


def test_an_error_and_a_skip_are_told_apart():
    text = (
        "import unittest\n\n\nclass C(unittest.TestCase):\n"
        '    def test_t1_ac1_boom(self):\n        """B."""\n        raise ValueError("bad")\n'
        '    @unittest.skip("later")\n'
        '    def test_t2_ac2_later(self):\n        """L."""\n'
    )

    result = run(text)

    assert {t.name: t.result for t in result.tests} == {
        "test_t1_ac1_boom": "error",
        "test_t2_ac2_later": "skipped",
    }


def test_a_test_file_that_cannot_be_imported_is_an_error_not_a_crash():
    result = run("import module_that_does_not_exist\n")

    assert result.ran and result.failed == 1
    assert "module_that_does_not_exist" in " ".join(
        t.message + " ".join(t.traceback_tail) for t in result.tests
    )


def test_the_build_files_are_laid_on_top_of_the_reference_copy():
    new = "def validate(path):\n    return 'new version'\n"
    text = body(
        "from agents.upload_validator import validate",
        "self.assertEqual(validate(1), 'new version')",
    )

    assert run(text, {MODIFY: new}).ok
    # Without the overlay the reference copy's own version answers True.
    assert not run(text).ok


def test_a_new_file_can_be_imported_and_crlf_text_is_kept():
    code = {"src/agents/excel_processor.py": "def rows():\r\n    return 3\r\n"}
    text = body(
        "from agents.excel_processor import rows",
        "self.assertEqual(rows(), 3)",
        "import pathlib",
        "raw = pathlib.Path('src/agents/excel_processor.py').read_bytes()",
        "self.assertIn(b'\\r\\n', raw)",
    )

    assert run(text, code).ok


def test_a_slow_test_is_ended_at_the_time_limit_and_named(tmp_path):
    """Test 6-14. The test also starts a child process: the whole tree must end."""
    pid_file = tmp_path / "child.pid"
    text = body(
        "import subprocess, sys, time",
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])",
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))",
        "time.sleep(60)",
    )
    started = time.monotonic()

    result = run(text, timeout=2)

    assert time.monotonic() - started < 15
    assert result.timed_out and not result.ok
    assert result.running_test == "test_t1_ac1_x"
    assert [(t.name, t.result) for t in result.tests] == [("test_t1_ac1_x", "error")]
    assert "Timed out after 2 seconds" in result.tests[0].message
    child = int(pid_file.read_text())
    time.sleep(0.3)
    assert not is_alive(child)  # the child process tree is gone too


def test_tests_that_finished_before_the_time_limit_are_kept():
    text = (
        "import time, unittest\n\n\nclass C(unittest.TestCase):\n"
        '    def test_t1_ac1_fast(self):\n        """F."""\n        self.assertTrue(True)\n'
        '    def test_t2_ac2_slow(self):\n        """S."""\n        time.sleep(60)\n'
    )

    result = run(text, timeout=2)

    assert result.timed_out and result.running_test == "test_t2_ac2_slow"
    assert {t.name: t.result for t in result.tests} == {
        "test_t1_ac1_fast": "pass",
        "test_t2_ac2_slow": "error",
    }


def test_no_api_key_or_da_setting_reaches_the_tests(monkeypatch):
    """Test 6-15."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-made-up")
    monkeypatch.setenv("DA_ONPREM_API_KEY", "made-up")
    monkeypatch.setenv("DA_LLM_PROVIDER", "fake")
    text = body(
        "import os",
        "self.assertNotIn('ANTHROPIC_API_KEY', os.environ)",
        "self.assertEqual([k for k in os.environ if k.startswith('DA_')], [])",
        "self.assertEqual(os.environ['HOME'], os.getcwd())",
    )

    result = run(text)

    assert result.ok, result.tests


def test_the_environment_holds_only_what_python_needs(tmp_path):
    env = da_sandbox.sandbox_environment(tmp_path)

    assert env["HOME"] == str(tmp_path) and env["TMPDIR"] == str(tmp_path)
    assert set(env) <= {
        "PATH",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "PYTHONIOENCODING",
        "PYTHONDONTWRITEBYTECODE",
        "SYSTEMROOT",
    }


def test_env_files_databases_git_and_keys_are_never_copied(tmp_path):
    """Test 6-16. The secrets are made here: Git would (rightly) refuse to hold them."""
    reference = tmp_path / "ref"
    shutil.copytree(REFERENCE, reference)
    src = reference / "src"
    (src / ".env").write_text("SECRET=made-up\n")
    (src / "data.db").write_text("not a real database")
    (src / "agents" / "client.key").write_text("made-up")
    (src / "configs" / "server.pem").write_text("made-up")
    (src / ".git").mkdir()
    (src / ".git" / "config").write_text("[core]\n")
    text = body(
        "import os",
        "for name in ('src/.env', 'src/data.db', 'src/agents/client.key', 'src/configs/server.pem',"
        " 'src/.git'):",
        "    self.assertFalse(os.path.exists(name), name)",
        "self.assertTrue(os.path.exists('src/agents/upload_validator.py'))",
    )

    assert run(text, reference=reference).ok


def test_output_is_cut_at_200_kb():
    """Test 6-17. One megabyte is printed."""
    result = run(body("print('x' * 1024 * 1024)"))

    assert result.ok and result.output_cut
    assert len(result.output.encode()) <= 200 * 1024


def test_the_sandbox_makes_its_own_tests_folder_and_leaves_the_reference_untouched():
    """Test 6-41. CodeVision has no tests folder; the sandbox builds its own, in its temp folder."""
    assert not (REFERENCE / "tests").exists()
    text = body(
        "import os",
        "self.assertTrue(os.path.isfile('tests/__init__.py'))",
        "self.assertTrue(os.path.isfile('tests/cvda_2026_0001/__init__.py'))",
        "self.assertTrue(os.path.isfile('tests/cvda_2026_0001/test_cvda_2026_0001.py'))",
    )

    result = run(text)

    assert result.ok and len(result.tests) == 1  # discovery found the test
    assert not (REFERENCE / "tests").exists()


def test_a_test_file_without_tests_is_not_a_pass():
    result = run("import unittest\n")

    assert result.ran and not result.ok
    assert "No tests were found" in result.error


def test_a_missing_reference_copy_cannot_start_and_is_not_the_codes_fault(tmp_path):
    result = run(reference=tmp_path / "nowhere", parent=tmp_path)

    assert not result.ran and not result.ok
    assert "The sandbox could not start" in result.error and "DA_SANDBOX_SOURCE_DIR" in result.error
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "path", ["../outside.py", "tests/x.py", "src/../../x.py", "/abs/x.py", "other/x.py"]
)
def test_paths_outside_src_or_under_tests_cannot_be_placed(path, tmp_path):
    result = run(code={path: "x = 1\n"}, parent=tmp_path)

    assert not result.ran and "may not be placed" in result.error
    assert list(tmp_path.iterdir()) == []


def test_the_alive_check_really_sees_a_live_process():
    """Guards the test above: without this, 'not alive' could be a check that never says alive."""
    assert is_alive(os.getpid())
    assert not is_alive(2**22 + 12345)


def test_a_process_that_dies_without_results_is_reported_as_an_error():
    result = run(body("import os", "os._exit(3)"))

    assert result.ran and result.failed == 1
    assert result.tests[0].name == "(test run)"


def test_a_child_left_running_by_a_test_that_ended_normally_is_still_ended(tmp_path):
    """Code review round 1: the whole process group is ended after every run, not only on a
    timeout."""
    pid_file = tmp_path / "child.pid"
    text = body(
        "import subprocess, sys",
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])",
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))",
    )

    result = run(text)

    assert result.ok and not result.timed_out  # the test itself passed and finished
    child = int(pid_file.read_text())
    time.sleep(0.3)
    assert not is_alive(child)


def test_the_windows_alive_check_reads_tasklist_and_never_signals(monkeypatch):
    """T1: on Windows is_alive must not call os.kill (signal 0 is Ctrl+C there)."""
    live = '"python.exe","4321","Console","1","20,000 K"\n'
    gone = "INFO: No tasks are running which match the specified criteria.\n"
    calls = []

    def forbidden(*args):
        raise AssertionError("os.kill must not be used on Windows")

    monkeypatch.setattr(os, "kill", forbidden)
    monkeypatch.setattr(sys.modules[__name__], "IS_WINDOWS", True)

    def fake_tasklist(pid):
        calls.append(pid)
        return live if pid == 4321 else gone

    monkeypatch.setattr(sys.modules[__name__], "run_tasklist", fake_tasklist)

    assert is_alive(4321) is True
    assert is_alive(99999) is False
    assert calls == [4321, 99999]


def test_tasklist_output_is_read_by_the_exact_process_id():
    row = '"cmd.exe","1234","Console","1","3,000 K"'
    assert tasklist_says_alive(row, 1234) is True
    assert tasklist_says_alive(row, 123) is False  # not a prefix match
    info = "INFO: No tasks are running which match the criteria."
    assert tasklist_says_alive(info, 1234) is False
    assert tasklist_says_alive("", 1234) is False
