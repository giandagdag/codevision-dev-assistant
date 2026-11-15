"""Fix 11-1 step 9 (AF-10, AF-11, AF-12b): Discover narrows to the capability that matches."""

from agents.da_discover_queries import match_capability, run_searches
from agents.da_search_index import FakeSearchIndex, IndexData, IndexPiece
from pydantic_classes.da_discovery_models import SearchFilters
from pydantic_classes.da_rulebook_models import Capability
from tests.test_da_discover_queries import make_record
from web.da_web_components import source_line

LIMITS = "src/agents/limits_expiry_report.py"
OTHER = "src/agents/other_expiry_report.py"


def cap(name, description, patterns):
    return Capability(
        name=name,
        description=description,
        named_senior="Lead",
        backup_senior="Deputy",
        path_patterns=patterns,
    )


CATALOG = [
    cap("Limits", "Customer limit set-up and expiry.", ["*limits*"]),
    cap("Uploads", "File upload screens.", ["*upload*"]),
]
PATHS = [LIMITS, OTHER, "src/layouts/upload_screen.py"]


def piece(number, path):
    return IndexPiece(
        piece_no=number,
        path=path,
        symbol="run_expiry",
        kind="code",
        language="python",
        snippet="def run_expiry(): list expiry report",
    )


def index():
    pieces = tuple(piece(n, p) for n, p in enumerate(PATHS[:2]))
    return FakeSearchIndex(IndexData(build_id="b1", built_at="", pieces=pieces))


def record(**changes):
    values = {"title": "Limits expiry report", "objective": "List expiry", "references": []}
    return make_record(**(values | changes))


def test_a_request_about_limits_matches_the_limits_capability_and_its_modules():
    name, modules = match_capability(record(), "", CATALOG, PATHS)

    assert name == "Limits"
    assert modules == [LIMITS]


def test_the_search_runs_filtered_first_and_labels_and_lists_capability_hits_first():
    result = run_searches(index(), record(), "", 5, CATALOG, PATHS)

    assert result.capability == "Limits"
    assert [hit.source_path for hit in result.hits][0] == LIMITS
    assert result.hits[0].capability == "Limits"
    assert result.hits[1].capability == ""  # the whole-index run still finds the other file
    assert "In capability: Limits" in source_line(result.hits[0])


def test_a_request_that_matches_no_capability_searches_as_today():
    other = record(title="Sparkle effect", objective="Logo glow", expected_behaviour="Shiny")

    narrowed = run_searches(index(), other, "", 5, CATALOG, PATHS)
    plain = run_searches(index(), other, "", 5)

    assert narrowed.capability == ""
    assert narrowed.hits == plain.hits
    assert all(hit.capability == "" for hit in narrowed.hits)


def test_a_filter_that_finds_nothing_leaves_the_whole_index_result():
    # The capability's module is not in this index at all: the second (whole index) run answers.
    thin = FakeSearchIndex(IndexData("b1", "", (piece(0, OTHER),)))

    result = run_searches(thin, record(), "", 5, CATALOG, PATHS)

    assert [hit.source_path for hit in result.hits] == [OTHER]


def test_the_discovery_round_uses_the_active_catalog(make_settings, published_rulebook):
    from agents.da_discover_flow import _search

    found, notes = _search(make_settings(), record(), "", index())

    assert found.capability == "Limits"
    assert notes == []  # the capability is not a limitation, so an escalation reason is unchanged


def test_the_module_filter_keeps_only_those_paths_in_the_pretend_index():
    hits = index().search("expiry report", "exact", SearchFilters(modules=[OTHER]), 5)

    assert [hit.source_path for hit in hits] == [OTHER]
