import tempfile

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
