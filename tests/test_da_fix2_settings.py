"""Phase 11 fix 2, step 1: the tagger role, its model row, the new settings (all made-up)."""

from agents.da_admin_forms import RESULT_SAVED, save_from_form
from agents.da_llm_client import ROLES, get_llm_client
from configs.da_config import load_settings
from db_table_functions.db_tbl_da_rulebook import get_active_version
from layouts.da_admin_build_tab import build_view

ADMIN = "admin1"


def test_the_tagger_is_a_known_role_and_the_fake_names_it(make_settings):
    assert "tagger" in ROLES
    assert get_llm_client("tagger", make_settings()).model == "fake-tagger"


def test_the_tagger_model_is_saved_from_the_build_form(db_path, published_rulebook):
    form = {"tagger_model": " qwen-tag-made-up "}

    result = save_from_form(db_path, "build", form, 1, ADMIN, "Tagger model")

    assert result.kind == RESULT_SAVED
    assert get_active_version(db_path).rulebook.policy.tagger_model == "qwen-tag-made-up"


def test_the_build_tab_shows_a_program_tagger_row(db_path, published_rulebook):
    assert "Program tagger" in str(build_view(get_active_version(db_path)))


def test_new_settings_default_to_empty_and_the_token_never_prints():
    settings = load_settings(env_file=None, environ={})
    found = (settings.tagger_max_modules, settings.sonar_url, settings.sonar_language)
    assert found == (500, "", "py")

    loaded = load_settings(
        env_file=None,
        environ={"DA_SONAR_URL": "http://sonar.example/", "DA_SONAR_TOKEN": "tok-made-up-123"},
    )
    assert loaded.sonar_url == "http://sonar.example"
    assert "tok-made-up-123" not in repr(loaded)
