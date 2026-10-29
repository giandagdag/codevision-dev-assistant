import pytest

from configs.da_config import PROJECT_ROOT, ConfigError, load_settings


def test_defaults_when_nothing_is_set():
    settings = load_settings(env_file=None, environ={})

    assert settings.llm_provider == "fake"
    assert settings.db_path == PROJECT_ROOT / "data" / "devassist.db"
    assert settings.claude_generator_model == ""
    assert settings.anthropic_api_key == ""
    assert settings.developer_id == "dev-home-01"


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


def test_developer_id_is_read_from_the_environment():
    settings = load_settings(env_file=None, environ={"DA_DEVELOPER_ID": "dev-0042"})

    assert settings.developer_id == "dev-0042"


# --- onprem settings (Phase 2C) ---


def test_onprem_defaults():
    settings = load_settings(env_file=None, environ={})

    assert settings.onprem_url == ""
    assert settings.onprem_model == ""
    assert settings.onprem_api_key == ""
    assert settings.onprem_auth_header == "Authorization"
    assert settings.onprem_auth_prefix == "Bearer "
    assert settings.onprem_verify is True
    assert settings.onprem_timeout_seconds == 120


def test_onprem_values_are_read():
    settings = load_settings(
        env_file=None,
        environ={
            "DA_ONPREM_URL": "https://llm.example.com/v1/chat/completions",
            "DA_ONPREM_MODEL": "some-model",
            "DA_ONPREM_API_KEY": "secret-key-123",
            "DA_ONPREM_AUTH_HEADER": "x-api-key",
            "DA_ONPREM_AUTH_PREFIX": "",
            "DA_ONPREM_TIMEOUT_SECONDS": "30",
        },
    )

    assert settings.onprem_url == "https://llm.example.com/v1/chat/completions"
    assert settings.onprem_model == "some-model"
    assert settings.onprem_api_key == "secret-key-123"
    assert settings.onprem_auth_header == "x-api-key"
    assert settings.onprem_auth_prefix == ""  # set but empty means no prefix
    assert settings.onprem_timeout_seconds == 30


def test_onprem_key_is_hidden_from_printouts():
    settings = load_settings(env_file=None, environ={"DA_ONPREM_API_KEY": "secret-key-123"})

    assert "secret-key-123" not in repr(settings)


def test_quoted_prefix_keeps_its_trailing_space_from_the_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('DA_ONPREM_AUTH_PREFIX="Token "\n', encoding="utf-8")

    settings = load_settings(env_file=env_file, environ={})

    assert settings.onprem_auth_prefix == "Token "


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("TRUE", True), ("", True), ("false", False), ("False", False)],
)
def test_onprem_verify_true_or_false(raw, expected):
    settings = load_settings(env_file=None, environ={"DA_ONPREM_VERIFY": raw})

    assert settings.onprem_verify is expected


def test_onprem_verify_path_is_kept_as_a_path():
    settings = load_settings(env_file=None, environ={"DA_ONPREM_VERIFY": "C:\\certs\\bank-ca.pem"})

    assert settings.onprem_verify == "C:\\certs\\bank-ca.pem"


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "1.5"])
def test_onprem_timeout_must_be_a_positive_whole_number(raw):
    with pytest.raises(ConfigError, match="DA_ONPREM_TIMEOUT_SECONDS"):
        load_settings(env_file=None, environ={"DA_ONPREM_TIMEOUT_SECONDS": raw})
