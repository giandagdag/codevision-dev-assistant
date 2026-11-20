"""Fix G4 L9, L10: search, filter, sort and the bulk plan (made-up cards, no AI)."""

from agents.da_admin_review import (
    ReviewFilter,
    bulk_plan,
    count_line,
    filter_ai_cards,
    filter_from_values,
    filter_requests,
    filter_suggestions,
    folder_of,
    top_folders,
)
from agents.da_admin_suggestions import Suggestion
from agents.da_admin_tag_cards import AiCard


def card(path, cap="Uploads", conf="high", summary="reads a file", when="2026-11-01"):
    return AiCard(path, cap, conf, summary, "because", when)


CARDS = [
    card("web/a.py", "Uploads", "low", "COBOL bridge", "2026-11-03"),
    card("agent_flows/b.py", "", "high", "makes a report", "2026-11-01"),
    card("web/c.py", "Reports", "medium", "shows a page", "2026-11-02"),
    card("agent_flows/d.py", "Reports", "high", "reads cobol copybook", "2026-11-04"),
]


def paths(cards):
    return [c.path for c in cards]


def test_search_matches_path_and_summary_any_case():
    f = filter_from_values(search="cobol")
    assert paths(filter_ai_cards(CARDS, f)) == ["agent_flows/d.py", "web/a.py"]
    assert count_line(2, 4) == "Showing 2 of 4"


def test_each_filter():
    assert paths(filter_ai_cards(CARDS, filter_from_values(confidence=["low"]))) == ["web/a.py"]
    assert paths(filter_ai_cards(CARDS, filter_from_values(proposal=["none"]))) == [
        "agent_flows/b.py"
    ]
    assert len(filter_ai_cards(CARDS, filter_from_values(proposal=["has"]))) == 3
    assert paths(filter_ai_cards(CARDS, filter_from_values(folder=["web"]))) == [
        "web/c.py",
        "web/a.py",
    ]
    assert filter_ai_cards(CARDS, filter_from_values(source=["request"])) == []


def test_each_sort_order():
    assert paths(filter_ai_cards(CARDS, ReviewFilter())) == [
        "agent_flows/b.py",
        "agent_flows/d.py",
        "web/c.py",
        "web/a.py",
    ]
    by_path = filter_from_values(sort="path")
    assert paths(filter_ai_cards(CARDS, by_path)) == [
        "agent_flows/b.py",
        "agent_flows/d.py",
        "web/a.py",
        "web/c.py",
    ]
    newest = filter_from_values(sort="newest")
    assert paths(filter_ai_cards(CARDS, newest))[0] == "agent_flows/d.py"


def test_suggestions_and_requests_follow_the_filters():
    sug = Suggestion("Letters", "prints letters", "low", {"web/x.py": "s"})
    assert filter_suggestions([sug], filter_from_values(proposal=["new"])) == [sug]
    assert filter_suggestions([sug], filter_from_values(proposal=["has"])) == []
    assert filter_suggestions([sug], filter_from_values(search="letters")) == [sug]

    class Row:
        path = "web/r.py"

    assert len(filter_requests([Row()], ReviewFilter())) == 1
    assert filter_requests([Row()], filter_from_values(confidence=["high"])) == []


def test_folders_and_active():
    assert folder_of("web/a.py") == "web" and folder_of("a.py") == ""
    assert top_folders(["web/a.py", "agent_flows/b.py", "c.py"]) == ["agent_flows", "web"]
    assert not ReviewFilter().active and filter_from_values(search="x").active


def test_bulk_plan_counts_and_skips():
    plan = bulk_plan(["web/a.py", "agent_flows/b.py", "web/c.py", "agent_flows/d.py", "x"], CARDS)
    assert len(plan.pairs) == 3 and plan.skipped == 1
    assert plan.counts == {"Uploads": 1, "Reports": 2}
