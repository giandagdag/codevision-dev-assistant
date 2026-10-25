"""Shared test helpers. Nothing here touches a real AI, the internet, .env, or the real database."""

from datetime import UTC, datetime

import anthropic
import pytest

from configs.da_config import Settings
from db_table_functions.db_tbl_da_rulebook import (
    SEED_RULEBOOK_FILE,
    load_rulebook_file,
    publish_first_version,
)

SEED_PUBLISHED_AT = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def block_real_claude(monkeypatch):
    """Safety net for rule R3: any test that forgets to mock Claude fails instead of calling it."""

    def refuse(*args, **kwargs):
        raise AssertionError("A test tried to create a real Anthropic client. Mock it instead.")

    monkeypatch.setattr(anthropic, "Anthropic", refuse)


@pytest.fixture
def db_path(tmp_path):
    """A fresh, empty database file in a temporary folder, deleted after the test."""
    return tmp_path / "test.db"


@pytest.fixture
def seed_rulebook():
    """The made-up starter rulebook from src/data, as a Rulebook object."""
    return load_rulebook_file(SEED_RULEBOOK_FILE)


@pytest.fixture
def published_rulebook(db_path, seed_rulebook):
    """Publish the seed as v1 in the test database. Requests can only be created after this."""
    return publish_first_version(
        db_path, seed_rulebook, "admin-0001", "Starter rulebook", now=SEED_PUBLISHED_AT
    )


@pytest.fixture
def make_settings(db_path):
    """Build Settings directly, with a temporary database, instead of reading .env."""

    def build(**changes):
        values = {
            "llm_provider": "fake",
            "claude_generator_model": "",
            "claude_reviewer_model": "",
            "db_path": db_path,
            "anthropic_api_key": "",
        }
        values.update(changes)
        return Settings(**values)

    return build
