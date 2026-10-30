"""Outcome rule (step 11a): the app picks the status from the findings, never the AI."""

import pytest

from agents.da_discover_flow import NOT_PROOF_LIMITATION, final_limitations, outcome_status
from pydantic_classes.da_discovery_models import Finding

SIMILAR = "SIMILAR_IMPLEMENTATION_FOUND"
NO_MATCH = "NO_RELIABLE_MATCH"


def finding(kind):
    return Finding(
        kind=kind, title="T", explanation="E", hit_ids=[1], confidence="medium"
    )


@pytest.mark.parametrize("kind", ["existing_capability", "similar_implementation"])
def test_an_existing_or_similar_finding_gives_similar_found(kind):
    assert outcome_status([finding("relevant_standard"), finding(kind)]) == SIMILAR


@pytest.mark.parametrize(
    "kinds", [[], ["relevant_standard"], ["affected_area", "relevant_standard"]]
)
def test_only_standards_or_areas_or_nothing_gives_no_reliable_match(kinds):
    assert outcome_status([finding(kind) for kind in kinds]) == NO_MATCH


def test_no_match_always_gets_the_not_proof_limitation_once():
    assert final_limitations([], NO_MATCH) == [NOT_PROOF_LIMITATION]
    assert final_limitations(["Only Python."], NO_MATCH) == ["Only Python.", NOT_PROOF_LIMITATION]
    assert final_limitations([NOT_PROOF_LIMITATION], NO_MATCH) == [NOT_PROOF_LIMITATION]


def test_a_match_does_not_get_the_not_proof_limitation():
    assert final_limitations(["Only Python."], SIMILAR) == ["Only Python."]


def test_the_limitation_text_is_the_spec_wording():
    assert NOT_PROOF_LIMITATION == (
        "No reliable match was found in approved sources. That is not proof it does not exist."
    )
