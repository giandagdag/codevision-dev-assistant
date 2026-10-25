from da_smoke_check import main, run_smoke_check


def test_fake_provider_prints_all_four_items(make_settings, capsys):
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
    assert "not configured yet" in output


def test_setup_problem_saves_nothing(make_settings, db_path):
    run_smoke_check(make_settings(llm_provider="onprem"))

    assert not db_path.exists()


def test_invalid_provider_lists_allowed_values(monkeypatch, capsys):
    monkeypatch.setenv("DA_LLM_PROVIDER", "qwen2")

    exit_code = main(env_file=None)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "fake, claude, onprem" in output
