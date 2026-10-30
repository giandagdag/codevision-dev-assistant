from agents.da_discover_queries import (
    MAX_HITS,
    MAX_QUERIES,
    build_queries,
    merge_hits,
    run_searches,
)
from agents.da_search_index import FakeSearchIndex
from pydantic_classes.da_discovery_models import SearchHit
from pydantic_classes.da_request_record_models import RequestRecord


def make_record(**changes):
    values = {
        "request_id": "CVDA-2026-0001",
        "rulebook_version": 1,
        "title": "Add Excel document processing",
        "objective": "Let users upload Excel workbooks.",
        "expected_behaviour": "Extract worksheet content into ingestion.",
        "references": ["Existing PDF processing"],
    }
    return RequestRecord(**(values | changes))


def as_pairs(queries):
    return [(q.mode, q.text) for q in queries]


def test_queries_come_from_title_references_objective_and_expected_behaviour():
    queries = build_queries(make_record())

    assert as_pairs(queries) == [
        ("exact", "Add Excel document processing"),
        ("meaning", "Let users upload Excel workbooks."),
        ("meaning", "Extract worksheet content into ingestion."),
        ("exact", "Existing PDF processing"),
    ]


def test_hint_adds_an_exact_and_a_meaning_query():
    queries = build_queries(make_record(), hint="batching helper")

    assert ("exact", "batching helper") in as_pairs(queries)
    assert ("meaning", "batching helper") in as_pairs(queries)
    assert len(queries) == 6


def test_queries_are_capped_at_6_and_the_hint_survives_the_cap():
    record = make_record(references=[f"Reference number {n}" for n in range(1, 9)])

    without_hint = build_queries(record)
    with_hint = build_queries(record, hint="my hint")

    assert len(without_hint) == len(with_hint) == MAX_QUERIES
    assert ("exact", "my hint") in as_pairs(with_hint)
    assert ("meaning", "my hint") in as_pairs(with_hint)


def test_empty_fields_and_duplicates_make_no_queries():
    queries = build_queries(make_record(objective="", expected_behaviour="", references=["x", "x"]))

    assert as_pairs(queries) == [("exact", "Add Excel document processing"), ("exact", "x")]


def test_long_text_is_cut_and_spaces_tidied():
    queries = build_queries(make_record(objective="word  " * 160))

    assert len(queries[1].text) <= 300 and "  " not in queries[1].text


def hit(path, symbol="", score=0.5, **changes):
    return SearchHit(
        source_path=path, symbol=symbol, kind="code", score=score, mode="exact", **changes
    )


def test_two_functions_in_one_file_stay_two_hits():
    merged = merge_hits([hit("a.py", "f"), hit("a.py", "g")])

    assert [(h.source_path, h.symbol) for h in merged] == [("a.py", "f"), ("a.py", "g")]


def test_same_path_and_symbol_keeps_the_best_score():
    merged = merge_hits([hit("a.py", "f", 0.3), hit("a.py", "f", 0.9), hit("a.py", "f", 0.5)])

    assert len(merged) == 1 and merged[0].score == 0.9


def test_best_12_are_kept_and_numbered_from_1():
    hits = [hit(f"f{n:02}.py", score=n / 100) for n in range(1, 21)]

    merged = merge_hits(hits)

    assert len(merged) == MAX_HITS
    assert [h.hit_id for h in merged] == list(range(1, 13))
    assert merged[0].score == 0.2 and merged[-1].score == 0.09


def test_run_searches_over_the_pretend_index_finds_the_pdf_processor():
    result = run_searches(FakeSearchIndex.from_file(), make_record(), "", top_k=5)

    symbols = {h.symbol for h in result.hits}
    assert "PdfProcessor.extract_text" in symbols
    assert [h.hit_id for h in result.hits] == list(range(1, len(result.hits) + 1))
    assert len(result.hits) <= MAX_HITS
    assert len(result.queries) == 4
