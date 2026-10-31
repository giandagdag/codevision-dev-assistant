from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_SETTINGS = {
    "DA_LLM_PROVIDER",
    "DA_CLAUDE_GENERATOR_MODEL",
    "DA_CLAUDE_REVIEWER_MODEL",
    "ANTHROPIC_API_KEY",
    "DA_DB_PATH",
    "DA_DEVELOPER_ID",
    "DA_ONPREM_URL",
    "DA_ONPREM_MODEL",
    "DA_ONPREM_API_KEY",
    "DA_ONPREM_AUTH_HEADER",
    "DA_ONPREM_AUTH_PREFIX",
    "DA_ONPREM_VERIFY",
    "DA_ONPREM_TIMEOUT_SECONDS",
    "DA_ONPREM_MAX_TOKENS",
    "DA_SEARCH_PROVIDER",
    "DA_SEARCH_TOP_K",
    "DA_DISCOVERY_MAX_ROUNDS",
}


def test_env_example_lists_every_setting():
    values = dotenv_values(PROJECT_ROOT / ".env.example")

    assert set(values) == EXPECTED_SETTINGS


def test_env_example_has_placeholder_key_only():
    values = dotenv_values(PROJECT_ROOT / ".env.example")

    # Real Anthropic keys start with "sk-". The example must never hold one.
    assert not values["ANTHROPIC_API_KEY"].startswith("sk-")
    assert values["ANTHROPIC_API_KEY"] == "your-key-here"


def test_gitignore_keeps_secrets_and_database_out():
    lines = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in lines
    assert ".venv/" in lines
    assert "data/*.db" in lines
    assert "logs/" in lines


def test_env_example_onprem_values_are_made_up_and_safe():
    values = dotenv_values(PROJECT_ROOT / ".env.example")

    # Rule R3: only example.com addresses, never a work address. No key, certificate check on.
    assert urlparse(values["DA_ONPREM_URL"]).hostname == "llm.example.com"
    assert values["DA_ONPREM_API_KEY"] == ""
    assert values["DA_ONPREM_VERIFY"] == "true"
    assert values["DA_ONPREM_AUTH_PREFIX"] == "Bearer "


def test_requests_is_pinned_for_work():
    lines = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()

    assert "requests==2.32.5" in lines
