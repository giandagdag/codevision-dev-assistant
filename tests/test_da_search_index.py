import json
import logging

import pytest

from agents.da_search_index import (
    FAKE_INDEX_FILE,
    FakeSearchIndex,
    IndexFormatError,
    SearchNotConfiguredError,
    drop_unsafe_hits,
    get_search_index,
    load_index_file,
    looks_secret,
    search_safely,
)
from configs.da_config import load_settings
from pydantic_classes.da_discovery_models import SearchFilters, SearchHit

FILTERS = SearchFilters()


@pytest.fixture(scope="module")
def index():
    return FakeSearchIndex.from_file()


def symbols(hits):
    return [hit.symbol or hit.source_path for hit in hits]


def test_pretend_index_loads_with_numbered_pieces():
    data = load_index_file(FAKE_INDEX_FILE)

    assert data.build_id
    assert 20 <= len(data.pieces) <= 30
    assert [p.piece_no for p in data.pieces] == list(range(len(data.pieces)))


def test_pretend_index_holds_the_special_pieces():
    pieces = load_index_file(FAKE_INDEX_FILE).pieces

    assert any(p.deprecated for p in pieces)
    assert any(p.restricted for p in pieces)
    assert any(looks_secret(p.path) for p in pieces)
    assert {"code", "standard", "doc", "config"} <= {p.kind for p in pieces}
    assert all(len(p.snippet) <= 500 for p in pieces)


def _write(tmp_path, pieces):
    path = tmp_path / "index.json"
    path.write_text(json.dumps({"build_id": "b1", "built_at": "x", "pieces": pieces}))
    return path


def _piece(number, **changes):
    return {"piece_no": number, "path": f"a{number}.py", "kind": "code"} | changes


def test_index_with_a_gap_is_refused(tmp_path):
    path = _write(tmp_path, [_piece(0), _piece(2)])

    with pytest.raises(IndexFormatError, match="out of order.*position 1.*number 2"):
        load_index_file(path)


def test_index_with_swapped_numbers_is_refused(tmp_path):
    path = _write(tmp_path, [_piece(1), _piece(0)])

    with pytest.raises(IndexFormatError, match="out of order"):
        load_index_file(path)


@pytest.mark.parametrize("text", ["not json", '{"pieces": []}', '{"build_id": "b", "pieces": [1]}'])
def test_unreadable_index_gives_a_plain_message(tmp_path, text):
    path = tmp_path / "index.json"
    path.write_text(text)

    with pytest.raises(IndexFormatError, match="could not be read"):
        load_index_file(path)


def test_exact_search_finds_the_expected_piece_first(index):
    hits = index.search("check upload file type", "exact", FILTERS, 5)

    assert symbols(hits)[0] == "UploadValidator.check_type"
    assert hits[0].mode == "exact"
    assert 0 < hits[0].score <= 1


def test_exact_search_is_whole_word_and_ignores_case(index):
    assert index.search("PDF", "exact", FILTERS, 5)
    assert index.search("pd", "exact", FILTERS, 5) == []


def test_meaning_search_finds_a_piece_by_synonym(index):
    # "parse" and "extract" share a group, "spreadsheet" is not in any piece.
    hits = index.search("parse pages", "meaning", FILTERS, 5)

    assert "PdfProcessor.extract_text" in symbols(hits)
    assert hits[0].mode == "meaning"


def test_meaning_search_finds_what_exact_search_misses(index):
    assert index.search("verify", "exact", FILTERS, 5) == []
    assert "UploadValidator.check_type" in symbols(index.search("verify", "meaning", FILTERS, 5))


def test_top_k_limits_the_hits(index):
    assert len(index.search("file", "exact", FILTERS, 2)) == 2


def test_empty_query_gives_nothing(index):
    assert index.search("   the of ", "meaning", FILTERS, 5) == []


def test_hit_version_comes_from_the_index_build_id(index):
    data = load_index_file(FAKE_INDEX_FILE)

    assert index.search("pdf", "exact", FILTERS, 1)[0].version == data.build_id


def test_deprecated_and_restricted_pieces_are_not_returned_by_default(index):
    hits = index.search("legacy payroll read pdf export", "exact", FILTERS, 30)

    assert not any(hit.deprecated or hit.restricted for hit in hits)


def test_deprecated_and_restricted_are_returned_only_when_the_filter_allows(index):
    open_filters = SearchFilters(include_deprecated=True, include_restricted=True)

    hits = index.search("legacy payroll", "exact", open_filters, 30)

    assert any(hit.deprecated for hit in hits) and any(hit.restricted for hit in hits)


def test_standards_still_show_when_the_language_is_python(index):
    assert any(hit.kind == "standard" for hit in index.search("standard", "exact", FILTERS, 5))


def test_language_filter_that_leaves_nothing_falls_back_for_meaning_only(tmp_path):
    path = _write(
        tmp_path,
        [
            _piece(0, language="python", tags=["validate", "upload"]),
            _piece(1, language="python", tags=["payroll"], restricted=True),
        ],
    )
    small = FakeSearchIndex.from_file(path)
    cobol_only = SearchFilters(languages=["cobol"])

    meaning = small.search("check upload", "meaning", cobol_only, 5)
    exact = small.search("upload", "exact", cobol_only, 5)

    assert [h.source_path for h in meaning] == ["a0.py"], "meaning falls back to permitted pieces"
    assert exact == [], "exact search has no fallback"
    assert small.search("payroll", "meaning", cobol_only, 5) == [], "restricted stays out"


def test_neutral_pieces_still_show_when_no_code_matches_the_language(index):
    hits = index.search("standard", "exact", SearchFilters(languages=["cobol"]), 5)

    assert hits and all(hit.kind != "code" for hit in hits)


def test_fallback_still_leaves_out_deprecated_and_restricted(index):
    meaning = index.search("read pdf payroll", "meaning", SearchFilters(languages=["cobol"]), 30)

    assert not any(hit.deprecated or hit.restricted for hit in meaning)


@pytest.mark.parametrize(
    "path",
    [".env", "config/.env.sample", "app/prod.env", "keys/server.pem", "keys/id.key",
     "app/secrets_loader.py", "app/Credentials.py"],
)
def test_secret_looking_paths_are_recognised(path):
    assert looks_secret(path)


@pytest.mark.parametrize("path", ["app/upload/upload_validator.py", "docs/environment.md"])
def test_normal_paths_are_not_secret_looking(path):
    assert not looks_secret(path)


def _hit(path="a.py", **changes):
    return SearchHit(source_path=path, kind="code", score=0.5, mode="exact", **changes)


def test_safety_filter_drops_deprecated_restricted_and_secret_hits():
    hits = [
        _hit("ok.py"),
        _hit("old.py", deprecated=True),
        _hit("hr.py", restricted=True),
        _hit("config/.env"),
        _hit("keys/a.pem"),
    ]

    kept, dropped = drop_unsafe_hits(hits)

    assert [h.source_path for h in kept] == ["ok.py"]
    assert dropped == 4


class _BadIndex:
    """An index that ignores our filters, to prove the safety filter works after any index."""

    def search(self, query, mode, filters, top_k):
        return [_hit("ok.py"), _hit("old.py", deprecated=True), _hit("config/.env.sample")]


def test_search_safely_filters_a_misbehaving_index_and_logs_only_a_count(caplog):
    with caplog.at_level(logging.INFO, logger="agents.da_search_index"):
        hits, dropped = search_safely(_BadIndex(), "q", "exact", FILTERS, 5)

    assert [h.source_path for h in hits] == ["ok.py"]
    assert dropped == 2
    assert "dropped 2" in caplog.text
    assert "old.py" not in caplog.text and ".env" not in caplog.text


def test_pretend_index_hits_with_open_filters_are_dropped_by_our_filter(index):
    open_filters = SearchFilters(include_deprecated=True, include_restricted=True)

    query = "legacy payroll sample settings"
    hits, dropped = search_safely(index, query, "exact", open_filters, 30)

    assert dropped >= 3
    assert not any(h.deprecated or h.restricted or looks_secret(h.source_path) for h in hits)


def test_get_search_index_gives_the_pretend_index_by_default():
    settings = load_settings(env_file=None, environ={})

    assert isinstance(get_search_index(settings), FakeSearchIndex)


def test_codevision_provider_without_index_files_says_to_build(tmp_path, monkeypatch):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path / "none"))
    settings = load_settings(env_file=None, environ={"DA_SEARCH_PROVIDER": "codevision"})

    with pytest.raises(SearchNotConfiguredError, match="needs building"):
        get_search_index(settings).search("x", "exact", FILTERS, 5)


def test_snippet_limit_for_stored_pieces_is_2000(tmp_path):
    assert load_index_file(_write(tmp_path, [_piece(0, snippet="x" * 501)]))
    assert load_index_file(_write(tmp_path, [_piece(0, snippet="x" * 2000)]))
    with pytest.raises(IndexFormatError, match="Piece 0 has a snippet that is too long"):
        load_index_file(_write(tmp_path, [_piece(0, snippet="x" * 2001)]))


def test_too_long_snippet_error_names_piece_length_limit_and_never_the_text(tmp_path):
    secret = "SECRETBODY" * 235  # 2,350 characters
    path = _write(tmp_path, [_piece(0), _piece(1, snippet=secret)])

    with pytest.raises(IndexFormatError) as caught:
        load_index_file(path)

    message = str(caught.value)
    assert "Piece 1" in message and "2,350" in message and "2,000" in message
    assert "SECRETBODY" not in message
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def _hit_of(tmp_path, snippet):
    piece = _piece(0, symbol="f", line_start=7, language="python", snippet=snippet)
    path = _write(tmp_path, [piece])
    index = FakeSearchIndex.from_file(path)
    return index, index.search("alpha", "exact", SearchFilters(languages=["python"]), 5)


def test_hit_snippet_is_cut_at_a_word_to_500_with_an_ellipsis_and_the_piece_keeps_its_text(
    tmp_path,
):
    text = "alpha " + "word " * 390  # about 1,950 characters
    index, hits = _hit_of(tmp_path, text)

    assert len(hits[0].snippet) <= 500 and hits[0].snippet.endswith("word…")
    assert (hits[0].symbol, hits[0].line_start) == ("f", 7)
    assert index._data.pieces[0].snippet == text  # Enhance and the tagger still see everything


def test_hit_snippet_with_no_spaces_is_cut_hard(tmp_path):
    _, hits = _hit_of(tmp_path, "x" * 1800 + " alpha")

    assert len(hits[0].snippet) == 500 and hits[0].snippet.endswith("…")


def test_short_snippet_is_unchanged_in_the_hit(tmp_path):
    _, hits = _hit_of(tmp_path, "alpha " + "y" * 74)  # 80 characters

    assert hits[0].snippet == "alpha " + "y" * 74


def test_other_shape_problems_still_refuse_the_whole_file(tmp_path):
    with pytest.raises(IndexFormatError, match="could not be read.*2000 characters"):
        load_index_file(_write(tmp_path, [_piece(0, kind="nonsense")]))
