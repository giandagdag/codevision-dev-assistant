"""Fix G9 step 14: every cite shows its meaning on hover and focus (F3, G9-14)."""

from datetime import UTC, datetime

from agents import da_tester_review as review
from layouts import da_tester_panel as tp
from pydantic_classes.da_approach_models import ApproachDecision
from tests.da_approach_samples import sample_record
from tests.da_build_play import make_approach


def _approach_with_decision():
    approach = make_approach()
    decision = ApproachDecision(
        question="Where is the check?",
        choice="In the upload step",
        custom=False,
        decided_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    return approach.model_copy(update={"decisions": [decision]})


def test_the_cite_notes_cover_decisions_reuse_exceptions_and_rules(seed_rulebook):
    record = sample_record().model_copy(
        update={"exceptions": ["RX-1: CV-PY-001 allowed for AC-2, approved by senior1, legacy"]}
    )

    notes = review.cite_notes(_approach_with_decision(), record, seed_rulebook.rules)

    assert notes["DD-1"] == "Design decision 1: Where is the check? → In the upload step"
    assert notes["RX-1"].startswith("RX-1: CV-PY-001 allowed for AC-2")
    assert notes["CV-PY-001"].startswith("CV-PY-001: ")
    assert tp.cite_tooltip("DD-1", notes) == notes["DD-1"]
    assert tp.cite_tooltip("PLAN:src/x.py", notes) == ""


def test_the_check_column_shows_the_check_name():
    assert tp.check_label(4) == "Check 4 · Matches the agreement"
    assert tp.check_label(9) == "Check 9"


def test_a_cite_with_a_meaning_can_be_focused_with_the_keyboard():
    cite = tp._cite("DD-1", {"DD-1": "Design decision 1: Q → A"})

    assert cite.label == "Design decision 1: Q → A"
    assert cite.events["focus"] is True and cite.events["hover"] is True
    assert cite.children.tabIndex == 0


def test_a_cite_without_a_meaning_is_plain_text():
    assert tp._cite("PLAN:src/x.py", {}).__class__.__name__ == "Text"
