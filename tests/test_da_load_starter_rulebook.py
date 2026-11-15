from da_load_starter_rulebook import load_starter_rulebook, main
from db_table_functions.db_tbl_da_rulebook import list_versions


def test_first_run_publishes_v1_from_the_seed(db_path, seed_rulebook):
    assert load_starter_rulebook(db_path) == "Rulebook v1 published."

    versions = list_versions(db_path)
    assert len(versions) == 1
    assert versions[0].saved_by == "setup-script"
    assert versions[0].rulebook == seed_rulebook


def test_second_run_changes_nothing(db_path):
    load_starter_rulebook(db_path)
    before = list_versions(db_path)

    message = load_starter_rulebook(db_path)

    assert message == "Rulebook already published (active v1). Nothing changed."
    assert list_versions(db_path) == before


def test_existing_version_is_left_alone(db_path, published_rulebook):
    assert "(active v1)" in load_starter_rulebook(db_path)


def test_main_reads_db_path_from_the_environment(db_path, monkeypatch, capsys):
    monkeypatch.setenv("DA_DB_PATH", str(db_path))

    assert main(env_file=None) == 0
    assert main(env_file=None) == 0

    output = capsys.readouterr().out.splitlines()
    assert output == [
        "Rulebook v1 published.",
        "Rulebook already published (active v1). Nothing changed.",
    ]


def _work_env(monkeypatch, db_path):
    monkeypatch.setenv("DA_DB_PATH", str(db_path))
    monkeypatch.setenv("DA_LLM_PROVIDER", "onprem")


def test_work_first_run_describes_codevision(db_path, monkeypatch):
    _work_env(monkeypatch, db_path)

    assert main(env_file=None, argv=[]) == 0

    charter = list_versions(db_path)[0].rulebook.charter
    assert "CodeVision" in charter.purpose
    assert "Harbour Loans" not in charter.purpose


def test_refresh_purpose_makes_new_version_then_nothing_to_change(
    db_path, monkeypatch, capsys
):
    load_starter_rulebook(db_path)  # the home seed, as the work database already holds
    _work_env(monkeypatch, db_path)

    assert main(env_file=None, argv=["--refresh-purpose"]) == 0
    assert main(env_file=None, argv=["--refresh-purpose"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("Rulebook v2 saved. Restore v1")
    assert lines[1] == "Nothing to change."
    versions = {v.version_number: v for v in list_versions(db_path)}
    assert len(versions) == 2
    assert "Harbour Loans" in versions[1].rulebook.charter.purpose  # v1 still there
    assert "CodeVision" in versions[2].rulebook.charter.purpose


def test_refresh_purpose_refused_at_home(db_path, monkeypatch, capsys):
    monkeypatch.setenv("DA_DB_PATH", str(db_path))
    monkeypatch.setenv("DA_LLM_PROVIDER", "fake")

    assert main(env_file=None, argv=["--refresh-purpose"]) == 1
    assert "only runs at work" in capsys.readouterr().out
