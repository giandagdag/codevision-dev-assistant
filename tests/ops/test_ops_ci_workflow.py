"""The GitHub Action is YAML and PyYAML is not a project library, so this checks the text."""

import re
from pathlib import Path

TEXT = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(
    encoding="utf-8")


def test_runs_on_phase_and_auto_branches_and_on_prs_into_the_two_targets():
    assert re.search(r'push:\s*\n\s*branches: \["auto/\*\*", "phase-\*"\]', TEXT)
    assert re.search(r'pull_request:\s*\n\s*branches: \["auto/phases-7-10", "main"\]', TEXT)


def test_runs_tests_ruff_and_smoke_check_on_python_3_14():
    assert 'python-version: "3.14"' in TEXT
    for command in ("python -m pytest", "python -m ruff check .", "python src/da_smoke_check.py"):
        assert f"run: {command}" in TEXT
    assert "requirements-home.txt" in TEXT


def test_uses_the_fake_provider_and_no_secrets_and_read_only_permissions():
    assert "DA_LLM_PROVIDER: fake" in TEXT
    assert "secrets." not in TEXT and "ANTHROPIC" not in TEXT and "${{" not in TEXT
    assert re.search(r"permissions:\s*\n\s*contents: read", TEXT)


def test_actions_are_pinned_to_a_version():
    uses = re.findall(r"uses: (\S+)", TEXT)
    assert uses and all(re.search(r"@v\d+$", u) for u in uses)


def test_has_a_job_name_the_merge_helper_will_see_as_a_check():
    assert re.search(r"^  checks:\s*$", TEXT, re.M)
