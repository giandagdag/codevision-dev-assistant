"""Phase 11 fix 2, step 2: the catalog search "What the code does" (AG-1, AG-2). Made-up only."""

import json
from pathlib import Path

import pytest

from agents import da_admin_meaning as meaning
from agents.da_admin_meaning import UNASSIGNED, meaning_search, modules_by_meaning, summary_score
from agents.da_search_index import FakeSearchIndex
from pydantic_classes.da_rulebook_models import Capability

EXPORT = "src/agents/docs_markdown_export.py"
CONVERT = "src/agents/docs_folder_to_md.py"
LIMITS = "src/agents/limits_batch.py"


def piece(no: int, path: str, symbol: str, tags: list[str], snippet: str) -> dict:
    return {
        "piece_no": no, "path": path, "symbol": symbol, "line_start": 3, "kind": "code",
        "language": "python", "tags": tags, "snippet": snippet,
    }


@pytest.fixture
def index(tmp_path: Path) -> FakeSearchIndex:
    """A made-up index: the two new modules match by their snippet words, not by file names."""
    pieces = [
        piece(0, LIMITS, "run_batch", ["batch", "limits"], "Runs the made-up limits batch."),
        piece(1, EXPORT, "write_report_file", ["markdown", "report"],
              "Creates a Markdown document with a heading and one bullet per line."),
        piece(2, CONVERT, "convert_folder", ["markdown", "folder"],
              "Creates one document next to each text note."),
    ]
    file = tmp_path / "index.json"
    file.write_text(json.dumps({"build_id": "t1", "built_at": "", "pieces": pieces}))
    return FakeSearchIndex.from_file(file)


def test_ag1_both_markdown_modules_are_in_the_top_3_by_their_words(index):
    caps = [Capability(name="Docs", description="d", named_senior="s1", path_patterns=[EXPORT])]

    hits = modules_by_meaning("creates markdown", index, caps)

    top = {h.path: h for h in hits[:3]}
    assert {EXPORT, CONVERT} <= set(top)
    assert LIMITS not in top
    assert (top[EXPORT].capability, top[CONVERT].capability) == ("Docs", UNASSIGNED)
    assert top[EXPORT].symbols == ("write_report_file",)


def test_ag1_shipped_index_and_shipped_script_find_both_markdown_modules():
    """The files that ship with the app, not an index built here (review 1, item 9)."""
    from agents.da_admin_tagger import FAKE_SCRIPT_FILE

    replies = json.loads(FAKE_SCRIPT_FILE.read_text(encoding="utf-8"))["replies"]
    tags = {p: {"summary": r["summary"]} for p, r in replies.items()}

    hits = modules_by_meaning("creates markdown", FakeSearchIndex.from_file(), [], tags)

    assert {EXPORT, CONVERT} <= {h.path for h in hits[:3]}


def test_ag1_the_search_never_calls_an_llm(index, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("an LLM was called")

    monkeypatch.setattr("agents.da_llm_client.get_llm_client", boom)

    assert modules_by_meaning("creates markdown", index, [])


def test_a_summary_alone_finds_a_module_and_is_labelled(index):
    tags = {"src/agents/other.py": {"summary": "Writes a Markdown file for the team."}}

    hits = modules_by_meaning("creates markdown", index, [], tags)
    extra = next(h for h in hits if h.path == "src/agents/other.py")

    assert extra.source == meaning.FROM_SUMMARY
    assert extra.summary == "Writes a Markdown file for the team."


def test_summary_score_needs_half_of_the_query_words():
    assert summary_score("Writes a Markdown file", "creates markdown") == 0.5
    assert summary_score("Sends an email", "creates markdown") == 0.0


def test_ag2_no_index_gives_one_plain_line(make_settings, tmp_path, monkeypatch):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path / "nothing"))
    settings = make_settings(search_provider="codevision")

    assert meaning_search("creates markdown", settings, [], {}) == ([], meaning.NEEDS_BUILDING)


def test_ag2_a_blank_query_is_quiet(make_settings):
    assert meaning_search("  ", make_settings(), [], {}) == ([], "")
