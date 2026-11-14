import json
import subprocess
from pathlib import Path

import faiss
import pytest

from agents.da_code_index import FAISS_NAME, PIECES_NAME, FakeEmbedder
from da_build_code_index import build_index

ROOT = Path(__file__).resolve().parents[1]


def make_source(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "agents").mkdir(parents=True)
    (src / "__pycache__").mkdir()
    loans = "def rate():\n    return 1\n\ndef term():\n    return 2\n"
    (src / "agents" / "loans.py").write_text(loans)
    (src / "agents" / "da_helper.py").write_text("def helper():\n    return 0\n")
    (src / "main.py").write_text("def start():\n    return 3\n")
    (src / "__pycache__" / "x.py").write_text("def junk():\n    pass\n")
    (src / "agents" / "secret_store.py").write_text("def secret():\n    pass\n")
    return src


def test_b1_16_builds_both_files_in_step(tmp_path):
    out = tmp_path / "out"
    summary = build_index(make_source(tmp_path), out, FakeEmbedder())
    data = json.loads((out / PIECES_NAME).read_text())
    paths = {p["path"] for p in data["pieces"]}
    assert summary.saved and data["count"] == len(data["pieces"]) == 3
    assert paths == {"agents/loans.py", "main.py"}
    assert data["build_id"].startswith("cv-") and data["vector_size"] == 8
    index = faiss.read_index(str(out / FAISS_NAME))
    assert index.ntotal == data["count"]
    assert [p["piece_no"] for p in data["pieces"]] == [0, 1, 2]
    # vector N is piece N: searching piece 1's own text finds position 1
    piece = data["pieces"][1]
    vector = FakeEmbedder().embed(f"{piece['path']} {piece['symbol']}\n{piece['snippet']}")
    import numpy as np

    _, found = index.search(np.array([vector], dtype="float32"), 1)
    assert found[0][0] == 1


class FailingEmbedder(FakeEmbedder):
    def __init__(self, fail_symbols):
        super().__init__()
        self.fail_symbols = fail_symbols

    def embed(self, text):
        if any(f"{s}\n" in text for s in self.fail_symbols):
            return None
        return super().embed(text)


def twenty_piece_source(tmp_path):
    src = tmp_path / "twenty"
    src.mkdir(exist_ok=True)
    body = "".join(f"def f{n}():\n    return {n}\n\n" for n in range(20))
    (src / "many.py").write_text(body)
    return src


def test_b1_17_one_of_twenty_skipped_is_saved(tmp_path):
    out = tmp_path / "out"
    summary = build_index(twenty_piece_source(tmp_path), out, FailingEmbedder(["f3"]))
    assert summary.saved and summary.count == 19
    assert summary.skipped == ["many.py f3"]
    assert json.loads((out / PIECES_NAME).read_text())["count"] == 19


def test_b1_17_over_ten_percent_saves_nothing(tmp_path):
    out = tmp_path / "out"
    build_index(twenty_piece_source(tmp_path), out, FakeEmbedder())  # an old index exists
    old = (out / PIECES_NAME).read_text()
    summary = build_index(
        twenty_piece_source(tmp_path), out, FailingEmbedder(["f1", "f2", "f3"])
    )
    assert not summary.saved and len(summary.skipped) == 3
    assert (out / PIECES_NAME).read_text() == old


def test_different_vector_size_stops_the_build(tmp_path):
    class Odd(FakeEmbedder):
        def embed(self, text):
            self.size = 4 if "f5" in text else 8
            return super().embed(text)

    summary = build_index(twenty_piece_source(tmp_path), tmp_path / "out", Odd())
    assert not summary.saved and "size" in summary.message
    assert not (tmp_path / "out").exists()


def test_index_folder_is_ignored_by_git():
    result = subprocess.run(
        ["git", "check-ignore", "src/data/da_code_index/da_code_index.faiss"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("name", ["faiss-cpu==1.12.0", "numpy==2.4.1"])
def test_requirements_pin_new_libraries(name):
    assert name in (ROOT / "requirements.txt").read_text()
