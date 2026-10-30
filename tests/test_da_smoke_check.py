import tempfile

import anthropic

from da_smoke_check import main, run_smoke_check
from tests.test_da_llm_client import FakeAnthropic, claude_settings


def test_fake_provider_prints_the_first_four_items(make_settings, capsys):
    exit_code = run_smoke_check(make_settings())

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "1. Active AI provider: fake" in output
    assert "2. New request created: CVDA-" in output
    assert "3. Audit events recorded for CVDA-2026-0001: 2" in output
    assert "developer  request_created" in output
    assert "system  smoke_check_ran" in output
    assert "4. AI reply from fake (fake-generator): [fake reply]" in output
    assert "Smoke check passed." in output


def test_fake_provider_prints_the_four_rulebook_items(make_settings, capsys):
    exit_code = run_smoke_check(make_settings())

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "5. Rulebook v1 published from the seed file" in output
    assert "6. Request CVDA-2026-0001 is pinned to v1" in output
    assert "7. v2 saved with CV-PY-002 changed to must_fix; request is still pinned to v1" in output
    assert '8. v1 restored as v3 ("Restored from v1"); versions, newest first: v3, v2, v1' in output


def test_successful_run_never_touches_the_real_database(make_settings, db_path):
    assert run_smoke_check(make_settings()) == 0

    assert not db_path.exists()


def test_runs_twice_in_a_row_and_cleans_up(make_settings, capsys, tmp_path, monkeypatch):
    # Point Python's temporary folder at our own, so we can see what is left afterwards.
    temp_root = tmp_path / "temp_root"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

    first = run_smoke_check(make_settings())
    second = run_smoke_check(make_settings())

    assert (first, second) == (0, 0)
    assert capsys.readouterr().out.count("Smoke check passed.") == 2
    # Both throwaway databases (and their folders) were deleted, so Windows let go of them.
    assert list(temp_root.iterdir()) == []


def test_fake_provider_prints_the_onprem_items_13_and_14(make_settings, capsys):
    exit_code = run_smoke_check(make_settings())

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "13. Ping with onprem against the pretend server: OK in" in output
    assert "(model fake-qwen, server 127.0.0.1)" in output
    assert "14. Conversation with onprem against the pretend server:" in output
    assert "reached CONFIRMED_FOR_DISCOVERY as record v1" in output
    assert output.index("12. ") < output.index("13. ") < output.index("14. ")


def test_fake_provider_prints_the_discover_items_15_to_17(make_settings, capsys):
    exit_code = run_smoke_check(make_settings())

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "15. Pretend index loaded; exact search found UploadValidator.check_type" in output
    assert "meaning search found" in output and "safety filter dropped" in output
    assert "16. CVDA-" in output
    assert "Discover reached SIMILAR_IMPLEMENTATION_FOUND (ai summary)" in output
    assert "then DISCOVERY_CONFIRMED" in output
    assert "record v1 unchanged: True" in output
    assert "17. With the pretend server in bad-json mode, CVDA-" in output
    assert "fell back to plain results (summary source: fallback)" in output
    assert output.index("14. ") < output.index("15. ") < output.index("16. ") < output.index("17. ")


def test_onprem_with_a_missing_certificate_file_stops_with_plain_message(make_settings, capsys):
    settings = make_settings(
        llm_provider="onprem",
        onprem_url="https://llm.example.com/v1/chat/completions",
        onprem_model="work-model",
        onprem_verify="no-such-file.pem",
    )

    exit_code = run_smoke_check(settings)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "DA_ONPREM_VERIFY points to 'no-such-file.pem'" in output
    assert "Traceback" not in output


def test_claude_without_key_stops_with_plain_message(make_settings, capsys):
    exit_code = run_smoke_check(make_settings(llm_provider="claude"))

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "ANTHROPIC_API_KEY is missing" in output
    assert "Traceback" not in output


def test_onprem_stops_with_plain_message(make_settings, capsys):
    exit_code = run_smoke_check(make_settings(llm_provider="onprem"))

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "DA_ONPREM_URL is missing" in output


def test_setup_problem_saves_nothing(make_settings, db_path):
    run_smoke_check(make_settings(llm_provider="onprem"))

    assert not db_path.exists()


def test_invalid_provider_lists_allowed_values(monkeypatch, capsys):
    monkeypatch.setenv("DA_LLM_PROVIDER", "qwen2")

    exit_code = main(env_file=None)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "fake, claude, onprem" in output


def test_fake_provider_prints_the_four_understand_items(make_settings, capsys):
    exit_code = run_smoke_check(make_settings())

    output = capsys.readouterr().out
    assert exit_code == 0
    assert (
        "9. Loader: Rulebook v1 published. "
        "Second run: Rulebook already published (active v1). Nothing changed."
    ) in output
    assert "10. Request CVDA-2026-0001 created (status CLARIFICATION_IN_PROGRESS)" in output
    assert "- Question 4 answered: status DECISION_REQUIRED" in output
    assert "(status DECISION_REQUIRED); chose \"Visible worksheets only\"" in output
    assert "(status CLARIFICATION_IN_PROGRESS)" in output
    assert (
        "12. Confirmed as record v1 (status CONFIRMED_FOR_DISCOVERY); editing v1 was refused: "
        "Confirmed request records are append-only and cannot be edited."
    ) in output


def test_understand_items_use_the_fake_script_whatever_the_provider(
    make_settings, capsys, monkeypatch
):
    # Items 1 to 8 need a working generator client; give the claude provider a mocked one.
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    exit_code = run_smoke_check(claude_settings(make_settings))

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "12. Confirmed as record v1" in output
