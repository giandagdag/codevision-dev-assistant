"""Shared test helpers. Nothing here touches a real AI, the internet, .env, or the real database."""

import anthropic
import pytest

from configs.da_config import Settings


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
