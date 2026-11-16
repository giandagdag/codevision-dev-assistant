"""Phase 11 fix 2, step 5: the AI scan cards, approve, approve all (AG-6, AG-7). Made-up only."""

from agents.da_admin_catalog import would_match
from agents.da_admin_tag_cards import (
    ai_cards,
    approve_all_high,
    approve_card,
    high_confidence_counts,
    reject_card,
)
from agents.da_admin_tag_store import read_tags, save_store
from callbacks.screen_callbacks.da_admin_page_callbacks import queue_data
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions
from layouts.da_admin_catalog_tab import queue_block

ADMIN = "admin-0001"


def _entry(capability, confidence, state="proposed"):
    return {
        "summary": f"Does {capability or 'nothing'}.",
        "proposed_capability": capability,
        "confidence": confidence,
        "reason": "because",
        "state": state,
    }


def _tags(tmp_path, entries):
    save_store({"modules": entries, "runs": []}, tmp_path)


def test_ag6_approve_saves_an_exact_path_pattern_and_the_module_shows_under_it(
    db_path, published_rulebook, make_settings, tmp_path
):
    _tags(tmp_path, {"zz/new_thing.py": _entry("Uploads", "medium")})

    result = approve_card(
        make_settings(), "zz/new_thing.py", "Uploads", ADMIN, 1, directory=tmp_path
    )

    assert result.kind == "resolved" and result.new_version == 2
    active = get_active_version(db_path)
    assert active.change_note == "AI scan: zz/new_thing.py to Uploads"
    assert would_match("zz/new_thing.py", active.rulebook.policy.capabilities) == "Uploads"
    assert read_tags(tmp_path)["zz/new_thing.py"]["state"] == "approved"
    assert ai_cards(tmp_path) == []


def test_ag7_approve_all_high_saves_exactly_one_version_with_the_count(
    db_path, published_rulebook, make_settings, tmp_path
):
    _tags(
        tmp_path,
        {
            **{f"zz/high{n}.py": _entry("Uploads", "high") for n in range(4)},
            "zz/medium.py": _entry("Uploads", "medium"),
            "zz/nofit.py": _entry("", "high"),
        },
    )
    assert high_confidence_counts(tmp_path) == {"Uploads": 4}

    result = approve_all_high(make_settings(), ADMIN, 1, directory=tmp_path)

    assert result.kind == "resolved" and result.new_version == 2
    assert len(list_versions(db_path)) == 2
    active = get_active_version(db_path)
    assert active.change_note == "AI scan: 4 programs approved (high confidence)"
    uploads = next(c for c in active.rulebook.policy.capabilities if c.name == "Uploads")
    assert all(f"zz/high{n}.py" in uploads.path_patterns for n in range(4))
    assert [c.path for c in ai_cards(tmp_path)] == ["zz/medium.py", "zz/nofit.py"]


def test_a_refused_save_leaves_every_card_open(
    db_path, published_rulebook, make_settings, tmp_path
):
    _tags(tmp_path, {"zz/a.py": _entry("Uploads", "high")})

    result = approve_card(make_settings(), "zz/a.py", "No such capability", ADMIN, 1, tmp_path)

    assert result.kind == "refused"
    assert len(ai_cards(tmp_path)) == 1 and len(list_versions(db_path)) == 1


def test_reject_closes_the_card_without_a_rulebook_change(db_path, published_rulebook, tmp_path):
    _tags(tmp_path, {"zz/a.py": _entry("", "low")})

    reject_card("zz/a.py", tmp_path)

    assert ai_cards(tmp_path) == [] and read_tags(tmp_path)["zz/a.py"]["state"] == "rejected"
    assert len(list_versions(db_path)) == 1


def test_cards_show_confidence_summary_and_hide_approve_when_nothing_fits(tmp_path):
    _tags(
        tmp_path,
        {"zz/fit.py": _entry("Uploads", "high"), "zz/nofit.py": _entry("", "low")},
    )
    queue = {"rows": [], "resolved": None, "dialog": None, "notice": [],
             "ai_cards": ai_cards(tmp_path)}  # fmt: skip

    shown = str(queue_block(queue, ["Uploads"]))

    assert "From the AI scan" in shown and "No capability fits" in shown
    assert "Does Uploads." in shown and "Approve all high-confidence (1)" in shown
    assert shown.count("'action': 'ai_approve'") == 1  # only the card with a capability


def test_a_module_chip_shows_its_ai_summary_as_a_tooltip(monkeypatch):
    from layouts import da_admin_catalog_tab as tab
    from pydantic_classes.da_rulebook_models import Capability

    monkeypatch.setattr(tab, "read_tags", lambda: {"src/up.py": {"summary": "Takes uploads."}})
    caps = [Capability(name="Uploads", description="d", named_senior="s",
                       path_patterns=["src/up.py"])]  # fmt: skip

    assert "Takes uploads." in str(tab.catalog_list(caps, ["src/up.py"]))


def test_overview_counts_the_ai_proposals(published_rulebook):
    from agents.da_admin_overview import overview_from

    shown = overview_from(published_rulebook, [], [], ai_proposals=3).attention
    assert "3 AI proposals to review" in " ".join(item.text for item in shown)
    assert not [i for i in overview_from(published_rulebook, [], []).attention if "AI " in i.text]


def test_queue_data_holds_the_ai_cards_key(db_path, published_rulebook, make_settings):
    assert "ai_cards" in queue_data(make_settings())
