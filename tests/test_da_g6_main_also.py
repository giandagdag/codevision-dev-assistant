"""Fix G6 M1: a module's main capability (first match) and its "also in" capabilities (G6-6)."""

from agents.da_admin_meaning import UNASSIGNED, capabilities_of, capability_of
from pydantic_classes.da_rulebook_models import Capability

PATH = "agent_flows/flw_md_to_fs.py"


def _cap(name: str, *patterns: str) -> Capability:
    return Capability(name=name, description="d", named_senior="Ana", path_patterns=list(patterns))


CATALOG = [_cap("Markdown", "agent_flows/flw_md_*.py"), _cap("Ingestion", "agent_flows/*.py"),
           _cap("Reports", "reports/*.py")]  # fmt: skip


def test_g6_6_main_is_the_first_match_and_the_rest_are_also():
    assert capabilities_of(PATH, CATALOG) == ("Markdown", ["Ingestion"])
    assert capability_of(PATH, CATALOG) == "Markdown"


def test_one_match_has_no_also_and_no_match_is_unassigned():
    assert capabilities_of("reports/a.py", CATALOG) == ("Reports", [])
    assert capabilities_of("zz/a.py", CATALOG) == (UNASSIGNED, [])


def test_a_module_with_a_main_is_never_counted_unassigned():
    paths = [PATH, "reports/a.py", "zz/a.py"]

    unassigned = [p for p in paths if capability_of(p, CATALOG) == UNASSIGNED]

    assert unassigned == ["zz/a.py"]
