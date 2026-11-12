"""Model per role (Phase 11, D-G): the Admin's name wins over .env; empty keeps the .env model.

Uses the onprem provider with a made-up URL. Building the client makes no network call (only
complete() does), and complete() is never called here.
"""

from dataclasses import replace

from agents.da_build_agent import get_build_client
from agents.da_build_loop import _Run
from agents.da_llm_client import get_llm_client
from agents.da_tester_agent import get_tester_client
from configs.da_config import load_settings
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_rulebook import publish_first_version, save_new_version


def onprem_settings():
    return load_settings(
        env_file=None,
        environ={
            "DA_LLM_PROVIDER": "onprem",
            "DA_ONPREM_URL": "http://made-up.invalid/v1/chat",
            "DA_ONPREM_MODEL": "env-generator",
            "DA_ONPREM_TESTER_MODEL": "env-tester",
        },
    )


def test_tester_uses_the_pinned_model_when_set():
    client = get_tester_client(onprem_settings(), "plan", "made-up-model")

    assert client.model == "made-up-model"


def test_tester_uses_the_env_model_when_the_pinned_one_is_empty():
    assert get_tester_client(onprem_settings(), "plan", "").model == "env-tester"
    assert get_tester_client(onprem_settings(), "plan").model == "env-tester"


def test_generator_uses_the_pinned_model_when_set():
    client = get_build_client(onprem_settings(), "generator", "made-up-gen")

    assert client.model == "made-up-gen"


def test_generator_uses_the_env_model_when_the_pinned_one_is_empty():
    assert get_build_client(onprem_settings(), "generator", "").model == "env-generator"


def test_build_loop_reads_the_model_from_the_pinned_version(db_path, seed_rulebook):
    # 11-21: a request created after the save uses the new name; an older one keeps the .env value.
    settings = replace(onprem_settings(), db_path=db_path)
    publish_first_version(db_path, seed_rulebook, "admin-0001", "Starter rulebook")
    older = create_request(db_path, "Older request", "dev-0001")
    policy = seed_rulebook.policy.model_copy(update={"tester_model": "made-up-model"})
    save_new_version(
        db_path, seed_rulebook.model_copy(update={"policy": policy}), 1, "admin-0001", "Tester"
    )
    newer = create_request(db_path, "Newer request", "dev-0001")
    calls = []

    def factory(settings, role, model=""):
        calls.append((role, model))
        return object()

    _Run(settings, older.request_id, factory, None).client("tester")
    _Run(settings, newer.request_id, factory, None).client("tester")
    _Run(settings, newer.request_id, factory, None).client("generator")

    assert calls == [("tester", ""), ("tester", "made-up-model"), ("generator", "")]


def test_the_fake_provider_ignores_the_name():
    settings = load_settings(env_file=None, environ={"DA_LLM_PROVIDER": "fake"})

    assert get_llm_client("generator", settings, "made-up-model").model == "fake-generator"
