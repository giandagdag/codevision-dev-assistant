"""Layer B: run the frozen tests on the server, in a separate process (spec section 6).

Like SBMJOB into a separate batch subsystem: the job has its own QTEMP (a temporary folder that
vanishes when it ends), no access to the interactive session's secrets, and the system ends it if
it runs too long.

HONEST LIMITS (also in the plan): a separate process with a time limit and an empty environment
is not a full jail. It does not block the network at operating-system level and does not cap
memory. Layer A's import and call rules plus "no keys in the environment" are the guard.
"""

import ast
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from agents.da_build_checks import find_test_methods
from agents.da_workspace_checks import path_problem
from da_logging import get_logger
from pydantic_classes.da_build_models import LayerBResult, TestOutcome

logger = get_logger(__name__)

OUTPUT_LIMIT_BYTES = 200 * 1024
RUNNER_SOURCE = Path(__file__).with_name("da_sandbox_runner.py")
RUNNER_NAME = "_da_runner.py"
# Always skipped when copying, on top of the policy's `build_sandbox_exclude`.
ALWAYS_SKIPPED = ("__pycache__", "*.pyc")
NOT_PROVEN_MESSAGE = "Not proven: no result recorded"
START_FAILED ="The sandbox could not start: "


class SandboxStartError(Exception):
    """The sandbox could not be built or started. Not the code's fault (spec section 6)."""


def run_tests(
    reference_dir: Path,
    code_files: dict[str, str],
    test_id: str,
    test_text: str,
    *,
    exclude: list[str],
    timeout_seconds: int,
    parent: Path | None = None,
) -> LayerBResult:
    """Build the temporary folder, run the tests in a separate process, and delete the folder.

    `reference_dir` is the CodeVision root that holds `src/` (the reference copy, decision D-A).
    `code_files` maps a path such as src/agents/x.py to this round's text. The folder is deleted
    whatever happened. A run that cannot start returns ran=False, never an exception.
    """
    try:
        root = Path(tempfile.mkdtemp(prefix="da_sandbox_", dir=parent))
    except OSError as error:
        return _could_not_start(f"the temporary folder could not be made ({error})")
    try:
        _build_folder(root, Path(reference_dir), code_files, test_id, test_text, exclude)
        return _run(root, test_id, timeout_seconds, _expected_names(test_text))
    except SandboxStartError as error:
        return _could_not_start(str(error))
    except OSError as error:
        return _could_not_start(f"{type(error).__name__}: {error}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _expected_names(test_text: str) -> list[str]:
    """The test methods the frozen file holds (F2: each one must report a result)."""
    try:
        return list(find_test_methods(ast.parse(test_text)))
    except SyntaxError:
        return []  # Layer A already refuses an unreadable test file


def _could_not_start(reason: str) -> LayerBResult:
    logger.warning("Sandbox did not start: %s", reason)
    return LayerBResult(ran=False, error=START_FAILED + reason)


def _build_folder(
    root: Path,
    reference_dir: Path,
    code_files: dict[str, str],
    test_id: str,
    test_text: str,
    exclude: list[str],
) -> None:
    source = reference_dir / "src"
    if not source.is_dir():
        raise SandboxStartError(
            f"the reference copy has no src folder ({reference_dir}). Check DA_SANDBOX_SOURCE_DIR."
        )
    # 1. a copy of the source tree, never secrets, databases or .git (policy exclude list)
    shutil.copytree(source, root / "src", ignore=shutil.ignore_patterns(*exclude, *ALWAYS_SKIPPED))
    # 2. this round's version of every planned code file, on top
    for path, text in code_files.items():
        _place(root, path, text)
    # 3. the sandbox's own tests folder (CodeVision has none, spec Q11)
    tests = root / "tests" / test_id
    tests.mkdir(parents=True)
    (root / "tests" / "__init__.py").write_text("")
    (tests / "__init__.py").write_text("")
    (tests / f"test_{test_id}.py").write_bytes(test_text.encode("utf-8"))
    # 4. our small runner
    shutil.copyfile(RUNNER_SOURCE, root / RUNNER_NAME)


def _place(root: Path, path: str, text: str) -> None:
    problem = path_problem(path)
    if problem or path.lower().startswith("tests/") or not path.startswith("src/"):
        raise SandboxStartError(f"the path {path!r} may not be placed in the sandbox")
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))  # bytes, so \r\n line endings stay as they are


def sandbox_environment(root: Path) -> dict[str, str]:
    """A fresh, nearly empty environment: only what Python needs to start. No DA_* settings, no
    API keys, nothing from the server's own environment except PATH (and SYSTEMROOT on Windows)."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(root),
        "TMPDIR": str(root),
        "TEMP": str(root),
        "TMP": str(root),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    return env


class _Capture:
    """Reads the process output on its own thread and keeps only the first 200 KB, so a test that
    prints without end can neither fill memory nor block on a full pipe."""

    def __init__(self, stream):
        self.data = bytearray()
        self.cut = False
        self._thread = threading.Thread(target=self._drain, args=(stream,), daemon=True)
        self._thread.start()

    def _drain(self, stream) -> None:
        while chunk := stream.read(65536):
            room = OUTPUT_LIMIT_BYTES - len(self.data)
            if room > 0:
                self.data += chunk[:room]
            if len(chunk) > room:
                self.cut = True

    def finish(self) -> str:
        self._thread.join(timeout=5)
        return bytes(self.data).decode("utf-8", errors="replace")


def _run(root: Path, test_id: str, timeout_seconds: int, expected: list[str]) -> LayerBResult:
    command = [sys.executable, "-I", str(root / RUNNER_NAME), str(root), test_id]
    options = {"start_new_session": True} if os.name != "nt" else {}
    try:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=sandbox_environment(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **options,
        )
    except OSError as error:
        raise SandboxStartError(f"Python could not be started ({error})") from error
    capture = _Capture(process.stdout)
    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        # Always end the whole group, not only on a timeout: a test that exits normally but
        # leaves a background child must not leave it running on the shared server.
        _end_process_tree(process)
    output = capture.finish()
    return _read_results(
        root, output, capture.cut, timed_out, timeout_seconds, process.returncode, expected
    )


def _end_process_tree(process: subprocess.Popen) -> None:
    """End the runner and everything it started. Linux: the whole process group. Windows:
    taskkill with /T (the tree)."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # it ended by itself a moment ago
    process.wait()


def _read_results(
    root: Path,
    output: str,
    cut: bool,
    timed_out: bool,
    timeout_seconds: int,
    returncode,
    expected: list[str],
) -> LayerBResult:
    tests = _read_outcomes(root / "results.json")
    running = _read_text(root / "running.txt")
    if timed_out:
        # The test that was running when time ran out counts as failed and is named.
        finished = {item.name for item in tests}
        if running and running not in finished:
            tests.append(
                TestOutcome(
                    name=running,
                    result="error",
                    message=f"Timed out after {timeout_seconds} seconds.",
                )
            )
        return LayerBResult(
            timed_out=True, running_test=running, output_cut=cut, output=output, tests=tests
        )
    error = ""
    if not tests and returncode not in (0, None):
        tests = [
            TestOutcome(
                name="(test run)",
                result="error",
                message="The test run stopped without results. " + output[-300:].strip(),
            )
        ]
    elif not tests:
        error = "No tests were found in the test file."
    else:
        # A frozen test with no result is "Not proven", never a quiet pass.
        reported = {item.name for item in tests}
        tests += [
            TestOutcome(name=name, result="not_proven", message=NOT_PROVEN_MESSAGE)
            for name in expected
            if name not in reported
        ]
    return LayerBResult(output_cut=cut, output=output, tests=tests, error=error)


def _read_outcomes(path: Path) -> list[TestOutcome]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [TestOutcome.model_validate(item) for item in data["tests"]]
    except ValueError, KeyError, TypeError:
        return []


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
