"""AF-12: a new module's suggested capability comes from what it imports."""

from agents import da_admin_suggest
from agents.da_admin_suggest import NO_MATCH, imported_names, suggest_capability
from pydantic_classes.da_rulebook_models import Capability


def caps():
    def make(name, pattern):
        return Capability(name=name, description="d", named_senior="a1", path_patterns=[pattern])

    return [make("Limits", "src/limits/*"), make("Reports", "src/reports/*")]


def test_imported_names_reads_both_forms():
    text = "import os\nfrom limits_core import x\n  import a.b as c\n"
    assert imported_names(text) == ["os", "limits_core", "a.b"]


def test_suggests_the_capability_it_imports_most(monkeypatch):
    paths = ["src/limits/limits_core.py", "src/limits/limits_rules.py", "src/reports/rep.py"]
    monkeypatch.setattr(da_admin_suggest, "module_paths", lambda scope="": paths)
    text = "from limits_core import a\nfrom limits_rules import b\nimport rep\n"
    name, reason = suggest_capability("src/new/x.py", caps(), text=text)
    assert name == "Limits" and reason == "Imports 2 modules from Limits"


def test_no_match_says_so(monkeypatch):
    monkeypatch.setattr(da_admin_suggest, "module_paths", lambda scope="": ["src/limits/a.py"])
    assert suggest_capability("src/new/x.py", caps(), text="import os\n") == ("", NO_MATCH)
