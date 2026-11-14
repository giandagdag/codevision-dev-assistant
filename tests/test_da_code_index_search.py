import json

import pytest

from agents.da_code_index import FAISS_NAME, PIECES_NAME, FakeEmbedder
from agents.da_search_index import CodeVisionSearchIndex, FakeSearchIndex, IndexNotBuiltError
from da_build_code_index import build_index
from pydantic_classes.da_discovery_models import SearchFilters

FILTERS = SearchFilters()


@pytest.fixture
def built(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "loans.py").write_text(
        "def validate_excel_upload():\n    return 1\n\ndef compute_rate():\n    return 2\n"
    )
    out = tmp_path / "out"
    build_index(src, out, FakeEmbedder())
    return out


def query_text(index_dir, number):
    piece = json.loads((index_dir / PIECES_NAME).read_text())["pieces"][number]
    return f"{piece['path']} {piece['symbol']}\n{piece['snippet']}"


def test_b1_18_meaning_hits_come_from_the_index_within_the_limit(built):
    index = CodeVisionSearchIndex(FakeEmbedder(), built)

    hits = index.search(query_text(built, 1), "meaning", FILTERS, 5)

    assert hits[0].symbol == "compute_rate" and hits[0].mode == "meaning"
    assert hits[0].score == 1.0  # same text, distance 0
    assert all(0 <= h.score <= 1 for h in hits)
    tight = CodeVisionSearchIndex(FakeEmbedder(), built, max_distance=0.0)
    assert [h.symbol for h in tight.search(query_text(built, 1), "meaning", FILTERS, 5)] == [
        "compute_rate"
    ]


def test_b1_18_an_empty_language_filter_does_not_hide_everything(built):
    index = CodeVisionSearchIndex(FakeEmbedder(), built)
    only_cobol = SearchFilters(languages=["cobol"])

    hits = index.search(query_text(built, 0), "meaning", only_cobol, 5)

    assert hits


def test_b1_19_exact_uses_the_practice_word_matching_on_the_real_pieces(built):
    index = CodeVisionSearchIndex(FakeEmbedder(), built)

    hits = index.search("validate excel", "exact", FILTERS, 5)

    assert [h.symbol for h in hits][:1] == ["validate_excel_upload"]
    assert isinstance(index._load()[0], FakeSearchIndex)


def test_b1_20_missing_files_say_to_build(tmp_path):
    with pytest.raises(IndexNotBuiltError, match="da_build_code_index.py"):
        CodeVisionSearchIndex(FakeEmbedder(), tmp_path).search("x", "exact", FILTERS, 5)


def test_b1_20_piece_count_differs_from_vector_count(built):
    path = built / PIECES_NAME
    data = json.loads(path.read_text())
    data["pieces"].pop()
    path.write_text(json.dumps(data))

    with pytest.raises(IndexNotBuiltError):
        CodeVisionSearchIndex(FakeEmbedder(), built).search("x", "exact", FILTERS, 5)
    assert (built / FAISS_NAME).exists()


def test_b1_21_embedding_failure_falls_back_to_exact_and_says_so(built):
    class Broken:
        def embed(self, text):
            return None

    index = CodeVisionSearchIndex(Broken(), built)

    hits = index.search("validate excel", "meaning", FILTERS, 5)

    assert hits and hits[0].mode == "exact"
    assert any("meaning search was not available" in note for note in index.notes)
    assert len(index.notes) == 1
    index.search("validate excel", "meaning", FILTERS, 5)
    assert len(index.notes) == 1  # said once
