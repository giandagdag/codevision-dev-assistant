"""Fix G3 step 2: an approved library the test Python cannot find (Layer A and the Approach prompt).

Plain checks with made-up names. No process is started: the "not installed" set is handed in."""

from agents import da_build_checks as checks
from agents import da_sandbox_python
from agents.da_approach_agent import ApproachContext, build_prompt, format_policy
from agents.da_approach_checks import PROPOSE
from pydantic_classes.da_build_models import Contract, ContractFile, ContractItem
from tests.da_approach_samples import sample_discovery, sample_record

PATH = "src/agents/excel_to_md.py"
CODE = "from openpyxl import load_workbook\n\n\ndef convert(path):\n    return load_workbook(path)\n"  # noqa: E501


def make_context(policy, **changes):
    item = ContractItem(name="convert", kind="function", args=["path"], summary="converts")
    contract = Contract(files=[ContractFile(path=PATH, items=[item])])
    return checks.LayerAContext([PATH], policy, contract, {"agents"}, **changes)


def test_g3_5_an_approved_library_that_is_not_installed_fails_layer_a(seed_rulebook):
    ctx = make_context(
        seed_rulebook.policy, not_installed=frozenset({"openpyxl"}), python_where="CodeVision .venv"
    )

    result = checks.check_layer_a({PATH: CODE}, ctx)

    [problem] = result.problems
    assert problem.code == "A4"
    assert problem.text == (
        "Line 1: 'openpyxl' is approved but not installed in CodeVision's Python "
        "(CodeVision .venv). Pick an installed library or ask the CodeVision team."
    )
    # the AI reads it in the next round's failure report
    report = checks.build_failure_report(result, None, [], "", [PATH])
    assert "approved but not installed" in checks.report_for_generator(report)


def test_g3_6_the_same_library_installed_passes(seed_rulebook):
    result = checks.check_layer_a({PATH: CODE}, make_context(seed_rulebook.policy))
    assert result.problems == []


def test_a_blocked_library_stays_blocked_not_reported_as_missing(seed_rulebook):
    policy = seed_rulebook.policy.model_copy(update={"build_blocked_imports": ["openpyxl"]})
    ctx = make_context(policy, not_installed=frozenset({"openpyxl"}))
    [problem] = checks.check_layer_a({PATH: CODE}, ctx).problems
    assert "blocked" in problem.text


def test_g3_7_the_approach_prompt_splits_installed_from_not_installed(seed_rulebook):
    text = format_policy(seed_rulebook.policy, frozenset({"openpyxl", "pandas"}))

    lines = text.splitlines()
    libraries = next(line for line in lines if line.startswith("- Approved libraries"))
    skipped = next(line for line in lines if line.startswith("- Approved, not installed"))
    assert "openpyxl" not in libraries and "pandas" not in libraries and "flask" in libraries
    assert "do not use" in skipped and "openpyxl" in skipped and "pandas" in skipped


def test_g3_7_nothing_missing_adds_no_extra_line(seed_rulebook):
    assert "not installed" not in format_policy(seed_rulebook.policy)


def test_the_full_prompt_carries_the_lines(seed_rulebook):
    context = ApproachContext(
        charter=seed_rulebook.charter, record=sample_record(), discovery=sample_discovery(),
        policy=seed_rulebook.policy, not_installed=frozenset({"openpyxl"}),
    )  # fmt: skip
    assert "Approved, not installed: do not use: openpyxl" in build_prompt(PROPOSE, context)


def test_approved_not_installed_asks_in_import_form(monkeypatch):
    asked = []
    monkeypatch.setattr(
        da_sandbox_python, "missing_libraries",
        lambda python, names: asked.append(names) or {"dash_iconify"},
    )  # fmt: skip

    found = da_sandbox_python.approved_not_installed(None, ["Dash-Iconify", "flask", "flask"])

    assert asked == [["dash_iconify", "flask"]] and found == frozenset({"dash_iconify"})
