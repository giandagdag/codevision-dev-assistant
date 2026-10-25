import pytest

from configs.da_config import PROJECT_ROOT, ConfigError, load_settings


def test_defaults_when_nothing_is_set():
    settings = load_settings(env_file=None, environ={})

    assert settings.llm_provider == "fake"
    assert settings.db_path == PROJECT_ROOT / "data" / "devassist.db"
    assert settings.claude_generator_model == ""
    assert settings.anthropic_api_key == ""


@pytest.mark.parametrize("provider", ["fake", "claude", "onprem"])
def test_allowed_providers_are_accepted(provider):
    settings = load_settings(env_file=None, environ={"DA_LLM_PROVIDER": provider})

    assert settings.llm_provider == provider


def test_invalid_provider_lists_the_allowed_values():
    with pytest.raises(ConfigError) as error:
        load_settings(env_file=None, environ={"DA_LLM_PROVIDER": "qwen2"})

    message = str(error.value)
    assert "qwen2" in message
    assert "fake, claude, onprem" in message


def test_values_are_read_from_the_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DA_LLM_PROVIDER=claude\nDA_CLAUDE_GENERATOR_MODEL=gen-model\n", encoding="utf-8"
    )

    settings = load_settings(env_file=env_file, environ={})

    assert settings.llm_provider == "claude"
    assert settings.claude_generator_model == "gen-model"


def test_environment_wins_over_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DA_LLM_PROVIDER=claude\n", encoding="utf-8")

    settings = load_settings(env_file=env_file, environ={"DA_LLM_PROVIDER": "onprem"})

    assert settings.llm_provider == "onprem"


def test_missing_env_file_falls_back_to_defaults(tmp_path):
    settings = load_settings(env_file=tmp_path / "no-such.env", environ={})

    assert settings.llm_provider == "fake"


def test_absolute_db_path_is_kept(tmp_path):
    db_file = tmp_path / "other.db"

    settings = load_settings(env_file=None, environ={"DA_DB_PATH": str(db_file)})

    assert settings.db_path == db_file


def test_api_key_is_hidden_when_settings_are_printed():
    settings = load_settings(env_file=None, environ={"ANTHROPIC_API_KEY": "test-secret-value"})

    assert settings.anthropic_api_key == "test-secret-value"
    assert "test-secret-value" not in repr(settings)
    assert "test-secret-value" not in str(settings)
