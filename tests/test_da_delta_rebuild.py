"""Delta rebuild (fix 11-3, D-B; AH-5, AH-6). Counting fake embedder, temp files, no AI."""

import json
from pathlib import Path

import faiss
import numpy as np

from agents.da_code_index import FAISS_NAME, PIECES_NAME, FakeEmbedder
from da_build_code_index import build_index


class Counting(FakeEmbedder):
    def __init__(self, size: int = 8) -> None:
        super().__init__(size)
        self.texts: list[str] = []

    def embed(self, text: str):
        self.texts.append(text)
        return super().embed(text)


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "code"
    source.mkdir()
    for name in ("a", "b", "c"):
        code = f"def f_{name}():\n    return '{name}'\n"
        (source / f"{name}.py").write_text(code, encoding="utf-8")
    return source


def _build(source, out, embedder, mode="full"):
    return build_index(source, out, embedder, say=lambda _t: None, mode=mode)


def _saved(out: Path):
    record = json.loads((out / PIECES_NAME).read_text(encoding="utf-8"))
    index = faiss.read_index(str(out / FAISS_NAME))
    return record, index.reconstruct_n(0, index.ntotal)


def test_delta_embeds_only_the_changed_file_and_matches_a_full_rebuild(tmp_path):
    source, out = _source(tmp_path), tmp_path / "idx"
    _build(source, out, Counting())
    (source / "b.py").write_text("def f_b():\n    return 'changed'\n", encoding="utf-8")
    counter = Counting()
    summary = _build(source, out, counter, "delta")
    assert summary.saved and summary.mode == "delta" and summary.reread == 1
    assert len(counter.texts) == 1 and "b.py" in counter.texts[0]
    record, vectors = _saved(out)
    full_out = tmp_path / "full"
    _build(source, full_out, Counting())
    full_record, full_vectors = _saved(full_out)
    assert [p["path"] for p in record["pieces"]] == [p["path"] for p in full_record["pieces"]]
    assert np.allclose(vectors, full_vectors)  # vector N still belongs to piece N


def test_delta_with_nothing_changed_embeds_nothing(tmp_path):
    source, out = _source(tmp_path), tmp_path / "idx"
    _build(source, out, Counting())
    counter = Counting()
    summary = _build(source, out, counter, "delta")
    assert summary.saved and counter.texts == [] and summary.reread == 0


def test_deleted_file_is_gone_from_both_files(tmp_path):
    source, out = _source(tmp_path), tmp_path / "idx"
    _build(source, out, Counting())
    (source / "c.py").unlink()
    _build(source, out, Counting(), "delta")
    record, vectors = _saved(out)
    assert {p["path"] for p in record["pieces"]} == {"a.py", "b.py"}
    assert len(vectors) == record["count"] == len(record["pieces"]) == 2


def test_delta_without_a_trusted_old_index_runs_full(tmp_path):
    source, out = _source(tmp_path), tmp_path / "idx"
    counter = Counting()
    assert _build(source, out, counter, "delta").mode == "full"  # nothing saved yet
    # an index saved before fix 3 has no hashes: Delta must not trust it
    record, _ = _saved(out)
    for piece in record["pieces"]:
        del piece["file_hash"]
    (out / PIECES_NAME).write_text(json.dumps(record), encoding="utf-8")
    assert _build(source, out, Counting(), "delta").mode == "full"
    # another embedder (here another vector size) forces Full too
    class Other(Counting):
        pass

    assert _build(source, out, Other(size=4), "delta").mode == "full"
    assert _saved(out)[0]["vector_size"] == 4


def test_stop_keeps_the_old_index(tmp_path):
    source, out = _source(tmp_path), tmp_path / "idx"
    _build(source, out, Counting())
    before = (out / PIECES_NAME).read_text(encoding="utf-8")
    summary = build_index(source, out, Counting(), say=lambda _t: None, stop=lambda: True)
    assert not summary.saved and "Stopped" in summary.message
    assert (out / PIECES_NAME).read_text(encoding="utf-8") == before


def test_progress_counts_only_embedded_pieces(tmp_path):
    source, out = _source(tmp_path), tmp_path / "idx"
    seen: list[tuple[int, int]] = []
    note = lambda done, total: seen.append((done, total))  # noqa: E731
    build_index(source, out, Counting(), say=lambda _t: None, progress=note)
    assert seen == [(1, 3), (2, 3), (3, 3)]
