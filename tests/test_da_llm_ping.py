"""The ping script (Phase 2C, spec 2.4)."""

from agents import da_llm_client
from agents.da_llm_client import LLMReply
from da_llm_ping import format_result, main, ping
from web.da_fake_onprem_server import running_fake_onprem_server

KEY = "home-test-key-not-real"


def set_onprem_env(monkeypatch, server, **extra):
    values = {
        "DA_LLM_PROVIDER": "onprem",
        "DA_ONPREM_URL": server.url,
        "DA_ONPREM_MODEL": "fake-qwen",
        "DA_ONPREM_TIMEOUT_SECONDS": "5",
        **extra,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_exit_0_and_a_short_report_against_the_pretend_server(monkeypatch, capsys):
    with running_fake_onprem_server() as server:
        set_onprem_env(monkeypatch, server)

        code = main(env_file=None)

    output = capsys.readouterr().out
    assert code == 0
    assert "Provider: onprem" in output
    assert "Model: fake-qwen" in output
    assert "Server: 127.0.0.1" in output
    assert "Time taken: " in output and " seconds" in output
    assert "Reply: OK" in output
    assert "Ping OK." in output


def test_report_shows_the_host_only_never_the_address_or_key(monkeypatch, capsys):
    with running_fake_onprem_server(key=KEY) as server:
        set_onprem_env(monkeypatch, server, DA_ONPREM_API_KEY=KEY)

        main(env_file=None)

    output = capsys.readouterr().out
    assert "/v1/chat/completions" not in output
    assert str(server.server_port) not in output
    assert KEY not in output


def test_exit_1_with_the_plain_error_when_the_server_refuses(monkeypatch, capsys, sleeps):
    with running_fake_onprem_server(key=KEY) as server:
        set_onprem_env(monkeypatch, server, DA_ONPREM_API_KEY="wrong-key-not-real")

        code = main(env_file=None)

    output = capsys.readouterr().out
    assert code == 1
    assert "Ping failed: The AI server refused the request (HTTP 401)" in output
    assert "wrong-key-not-real" not in output
    assert "Traceback" not in output


def test_exit_1_when_nothing_is_listening(monkeypatch, capsys, sleeps):
    with running_fake_onprem_server() as server:
        set_onprem_env(monkeypatch, server)

    code = main(env_file=None)

    assert code == 1
    assert "Ping failed: Cannot connect" in capsys.readouterr().out


def test_exit_1_when_a_setting_is_missing(monkeypatch, capsys):
    monkeypatch.setenv("DA_LLM_PROVIDER", "onprem")
    monkeypatch.delenv("DA_ONPREM_URL", raising=False)

    code = main(env_file=None)

    assert code == 1
    assert "Ping failed: DA_ONPREM_URL is missing" in capsys.readouterr().out


def test_exit_1_when_a_setting_is_not_allowed(monkeypatch, capsys):
    monkeypatch.setenv("DA_LLM_PROVIDER", "qwen2")

    assert main(env_file=None) == 1
    assert "Ping failed" in capsys.readouterr().out


def test_works_with_the_fake_provider_too(monkeypatch, capsys):
    monkeypatch.setenv("DA_LLM_PROVIDER", "fake")

    code = main(env_file=None)

    output = capsys.readouterr().out
    assert code == 0
    assert "Provider: fake" in output and "Server: (none)" in output
    assert "Reply: [fake reply] ping" in output


def test_reply_is_cut_at_200_characters(make_settings, monkeypatch):
    class Wordy:
        model = "wordy"

        def complete(self, prompt, system=None):
            return LLMReply(text="x" * 500, provider="fake", model=self.model)

    monkeypatch.setattr(da_llm_client, "FakeLLMClient", lambda role: Wordy())

    lines = format_result(ping(make_settings()))

    assert "Reply: " + "x" * 200 in lines
