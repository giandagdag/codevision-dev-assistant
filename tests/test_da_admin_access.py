import logging

import pytest

from agents.da_admin_access import is_admin
from configs.da_config import ConfigError, load_settings


def settings_with(**env):
    return load_settings(env_file=None, environ={"DA_LLM_PROVIDER": "fake", **env})


def test_env_list_lets_a_listed_user_in():
    settings = settings_with(DA_ADMIN_IDS="dev-home-01, dev-home-02")

    assert is_admin(settings, "dev-home-01")
    assert is_admin(settings, "dev-home-02")


def test_user_not_in_the_list_is_refused():
    assert not is_admin(settings_with(DA_ADMIN_IDS="dev-home-01"), "someone-else")


def test_empty_list_means_nobody():
    settings = settings_with()

    assert settings.admin_ids == ()
    assert not is_admin(settings, "dev-home-01")
    assert not is_admin(settings, "")


def test_codevision_placeholder_refuses_everybody_and_logs(caplog):
    settings = settings_with(DA_ADMIN_SOURCE="codevision", DA_ADMIN_IDS="dev-home-01")

    with caplog.at_level(logging.WARNING):
        assert not is_admin(settings, "dev-home-01")

    assert "Admin access is not configured yet" in caplog.text


def test_unknown_admin_source_is_refused_at_start():
    with pytest.raises(ConfigError, match="DA_ADMIN_SOURCE is 'ldap'"):
        settings_with(DA_ADMIN_SOURCE="ldap")
