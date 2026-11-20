"""Which Python runs the tests (Fix G3).

Like submitting a job with the right library list: CodeVision's code must be tested with
CodeVision's Python and libraries, so the developer never installs anything twice.
`DA_CODEVISION_PYTHON` set -> that Python. Not set -> the Developer Assistant's own (home setup).
Standard library only, because it also asks the test Python questions in a small child process.
"""

import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MIN_VERSION = (3, 14)
PROBE_SECONDS = 10
MISSING_FILE_TEXT = "DA_CODEVISION_PYTHON points to a file that does not exist"
NO_VERSION_TEXT = "could not read the version of the test Python"
_VERSION_CODE = "import sys; print('.'.join(map(str, sys.version_info[:3])))"
# One call for all names. A name that cannot even be looked up counts as not found.
_FIND_CODE = (
    "import importlib.util as u, sys\n"
    "def found(n):\n"
    "    try:\n"
    "        return u.find_spec(n) is not None\n"
    "    except (ImportError, ValueError):\n"
    "        return False\n"
    "print('\\n'.join(n for n in sys.argv[1:] if not found(n)))\n"
)
_versions: dict[tuple[str, float], tuple[int, ...] | None] = {}


@dataclass(frozen=True)
class TestPython:
    """The Python the sandbox starts. `error` is empty when it can be used."""

    __test__ = False  # not a pytest class, whatever the name says

    path: str
    source: str  # "codevision" or "own"
    version: tuple[int, ...] = ()
    error: str = ""

    @property
    def where(self) -> str:
        """Safe words for the screen: never the real path."""
        return "CodeVision .venv" if self.source == "codevision" else "Developer Assistant .venv"

    @property
    def owner(self) -> str:
        return "CodeVision's Python" if self.source == "codevision" else (
            "The Developer Assistant's Python"
        )

    @property
    def label(self) -> str:
        who = "CodeVision's" if self.source == "codevision" else "Developer Assistant's"
        return f"{who} Python {'.'.join(map(str, self.version))}".strip()


def test_python(settings) -> TestPython:
    """The Python for every sandbox run, or the reason it cannot be used."""
    chosen = getattr(settings, "codevision_python", "") if settings is not None else ""
    if not chosen:
        return _checked(TestPython(sys.executable, "own", tuple(sys.version_info[:3])))
    if not Path(chosen).is_file():
        return TestPython(chosen, "codevision", error=MISSING_FILE_TEXT)
    version = _version_of(chosen)
    if version is None:
        return TestPython(chosen, "codevision", error=NO_VERSION_TEXT)
    return _checked(TestPython(chosen, "codevision", version))


def _checked(found: TestPython) -> TestPython:
    if found.version[:2] < MIN_VERSION:
        shown = ".".join(map(str, found.version))
        return TestPython(
            found.path, found.source, found.version,
            f"The test Python is version {shown}. Python 3.14 or newer is needed.",
        )  # fmt: skip
    return found


def _version_of(path: str) -> tuple[int, ...] | None:
    """Asks the Python once per file (cached by path and file time); None when it cannot say."""
    try:
        key = (path, Path(path).stat().st_mtime)
    except OSError:
        return None
    if key not in _versions:
        out = _probe(path, ["-c", _VERSION_CODE])
        try:
            _versions[key] = tuple(int(part) for part in (out or "").strip().split("."))
        except ValueError:
            return None  # not cached: a later try may work
    return _versions[key]


def _probe(path: str, args: list[str]) -> str | None:
    """Runs the test Python with a bare environment. None when it fails or is too slow."""
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    try:
        done = subprocess.run(
            [path, "-I", *args], capture_output=True, text=True, timeout=PROBE_SECONDS,
            env=env, stdin=subprocess.DEVNULL, check=False,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def missing_libraries(python: TestPython, names: list[str]) -> set[str]:
    """Which of `names` (import names) the test Python cannot find. One call for all of them, never
    cached (installing a library does not change the file time). A failed call says none are
    missing: the real run then gives the load-error words."""
    if not names or python.error:
        return set()
    if python.path == sys.executable:
        return {n for n in names if _in_process_missing(n)}
    out = _probe(python.path, ["-c", _FIND_CODE, *names])
    return {line.strip() for line in (out or "").splitlines() if line.strip()}


def approved_not_installed(settings, approved: list[str]) -> frozenset[str]:
    """The approved libraries (import form: lower case, `-` as `_`) the test Python lacks."""
    names = sorted({name.strip().lower().replace("-", "_") for name in approved})
    return frozenset(missing_libraries(test_python(settings), names))


def _in_process_missing(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is None
    except (ImportError, ValueError):
        return True
