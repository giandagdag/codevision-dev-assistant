"""Embedder interface for the real CodeVision index (fix B1, I1).

AS400 picture: an embedder is like a program that turns a record into a sort key.
The fake one runs at home; the work one calls CodeVision's own embedding service.
Our code never logs the text it embeds (it may be work code).
"""

import hashlib
from pathlib import Path
from typing import Protocol

WORK_ONLY_MESSAGE = "This only works inside CodeVision at work."
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
    """Calls CodeVision's `agents.a_vector.create_embeddings`; only exists at work."""

    def embed(self, text: str) -> list[float] | None:
        try:
            # Imported here on purpose: at home this module does not exist.
            from agents.a_vector import create_embeddings
        except ImportError as error:
            raise RuntimeError(WORK_ONLY_MESSAGE) from error
        result = create_embeddings(text)
        if result is None:  # CodeVision gives None when every retry failed
            return None
        return [float(value) for value in result[0]]  # shape (1, size)
