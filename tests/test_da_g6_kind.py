"""Fix G6 C3: the capability kind (Business / Shared foundation)."""

import pytest
from pydantic import ValidationError

from agents.da_admin_forms import _capability_form_rows, capability_rows
from pydantic_classes.da_rulebook_models import Capability

BASE = {"name": "Config", "description": "d", "named_senior": "s", "path_patterns": ["a/*"]}


def test_an_old_capability_without_kind_reads_business():
    assert Capability(**BASE).kind == "Business"


def test_only_the_two_kinds_are_accepted():
    assert Capability(**BASE, kind="Shared foundation").kind == "Shared foundation"
    with pytest.raises(ValidationError):
        Capability(**BASE, kind="Other")


def test_kind_survives_the_catalog_form(published_rulebook):
    policy = published_rulebook.rulebook.policy
    rows = capability_rows(policy)
    rows[0]["kind"] = "Shared foundation"

    saved = _capability_form_rows(rows)

    assert saved[0]["kind"] == "Shared foundation"
    assert all(row["kind"] == "Business" for row in saved[1:])


def test_an_empty_new_row_is_still_dropped():
    assert _capability_form_rows([{"name": "", "kind": "Business", "path_patterns": ""}]) == []
