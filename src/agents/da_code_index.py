"""Embedder interface for the real CodeVision index (fix B1, I1).

AS400 picture: an embedder is like a program that turns a record into a sort key.
The fake one runs at home; the work one calls CodeVision's own embedding service.
Our code never logs the text it embeds (it may be work code).
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from configs.da_config import load_settings
from da_logging import get_logger

logger = get_logger(__name__)

WORK_ONLY_MESSAGE = "This only works inside CodeVision at work."
HELPER_DIED_MESSAGE = (
    "CodeVision's embedder stopped twice. Not saved; the old index stays."
)
HELPER = Path(__file__).resolve().parents[1] / "da_embed_worker.py"
# Our own folder: we never read or change CodeVision's vector files.
DEFAULT_INDEX_DIR = Path(__file__).resolve().parents[1] / "data" / "da_code_index"
FAISS_NAME = "da_code_index.faiss"
PIECES_NAME = "da_code_index.json"


class Embedder(Protocol):
    def embed(self, text: str) -> list[float] | None:
        """Return the vector for the text, or None when it could not be made."""


class FakeEmbedder:
    """Same text gives the same vector. No network. Tests only."""

    def __init__(self, size: int = 8) -> None:
        self.size = size

    def embed(self, text: str) -> list[float] | None:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255 for i in range(self.size)]


class WorkEmbedder:
    """Asks CodeVision's own embedder through a helper process (fix 11-3, D-A).

    Why a process: CodeVision and the DA both have packages named `agents` and `configs`, so inside
    our process CodeVision's `a_vector` can never be found. The helper runs under CodeVision's
    Python with only CodeVision's folder on its search path. One helper serves the whole build."""

    def __init__(self, src: str = "", python: str = "") -> None:
        self._src, self._python = src, python
        self._process: subprocess.Popen | None = None
        self._restarts = 0

    def embed(self, text: str) -> list[float] | None:
        while True:
            try:
                return self._ask(text)
            except (OSError, ValueError, EOFError):  # the helper died or sent rubbish
                self.close()
                if self._restarts >= 1:
                    raise RuntimeError(HELPER_DIED_MESSAGE) from None
                self._restarts += 1
                logger.warning("CodeVision's embedder helper stopped; starting it once more")

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            process.stdin.close()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
        process.stdout.close()

    def _ask(self, text: str) -> list[float] | None:
        process = self._process or self._start()
        process.stdin.write(json.dumps({"text": text}) + "\n")
        process.stdin.flush()
        return json.loads(self._read_line(process))["vector"]

    @staticmethod
    def _read_line(process: subprocess.Popen) -> str:
        line = process.stdout.readline()
        if not line:
            raise EOFError("helper closed")
        return line

    def _start(self) -> subprocess.Popen:
        src, python = self._src, self._python
        if not src:
            settings = load_settings()
            src, python = settings.codevision_src, python or settings.codevision_python
        if not src or not Path(src).is_dir():
            raise RuntimeError(
                "Where CodeVision's code lives is not set or not found. "
                "Set DA_CODEVISION_SRC (the CodeVision src folder with agents, tools, configs)."
            )
        # An argument list (never one joined string) so a path with spaces works. -I keeps our own
        # src folder off the helper's search path.
        process = subprocess.Popen(
            [python or sys.executable, "-I", str(HELPER), src],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", cwd=src,
        )
        try:
            first = json.loads(self._read_line(process))
        except (EOFError, ValueError, OSError):
            process.kill()
            raise RuntimeError(
                "CodeVision's embedder could not start. Check DA_CODEVISION_PYTHON "
                "(the Python that runs CodeVision)."
            ) from None
        if "error" in first:
            process.kill()
            raise RuntimeError(first["error"])
        self._process = process
        return process
