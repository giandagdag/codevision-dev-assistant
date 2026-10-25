from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_SETTINGS = {
    "DA_LLM_PROVIDER",
    "DA_CLAUDE_GENERATOR_MODEL",
    "DA_CLAUDE_REVIEWER_MODEL",
    "ANTHROPIC_API_KEY",
    "DA_DB_PATH",
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
