"""AF-2: no raw field or setting names (DA_..., build_max_rounds) in the text the Admin draws."""

import pytest

from agents.da_admin_labels import raw_names_in
from layouts.da_admin_page import ADMIN_TABS, admin_page, tab_content
from pydantic_classes.da_rulebook_models import Rulebook
from tests.test_da_admin_page import walk

NEW_POLICY_FIELDS = (
    "index_repo", "index_branch", "index_folder_scope", "index_refresh_mode", "index_exclusions",
)
TEXT_PROPS = ("label", "title", "description", "placeholder")
# Folder and library names that rules name on purpose: they are the thing, not a setting.
CODE_NAMES = frozenset(
    {"db_table_functions", "pydantic_classes", "dash_iconify", "dash_mantine_components"}
)


def _is_code_or_path(line: str) -> bool:
    """Golden example code, module chips and folder paths are code chips, allowed to hold names."""
    return any(mark in line for mark in "(=/") or ".py" in line or line.startswith("from ")


def shown_text(node) -> str:
    """Only words a person reads: text children and the label-like props, never component ids."""
    parts = []
    for item in walk(node):
        if isinstance(item, str):
            parts.append(item)
            continue
        parts += [str(v) for p in TEXT_PROPS if isinstance(v := getattr(item, p, None), str)]
    return "\n".join(parts)


def _old_version(version):
    old = version.rulebook.model_dump(mode="json")
    for name in NEW_POLICY_FIELDS:
        del old["policy"][name]
    del old["brand_constants"]
    for example in old["golden_examples"]:
        del example["program_type"]
        del example["module_path"]
    return version.model_copy(update={"rulebook": Rulebook.model_validate(old)})


def _raw_names(version) -> list[str]:
    """The drawn lines that hold a raw name (the whole line, so a failure shows where)."""
    texts = [shown_text(admin_page(version))]
    for tab, _, _ in ADMIN_TABS:
        if tab not in ("overview", "history"):
            texts.append(shown_text(tab_content(tab, version, editable=True)))
    lines = {line for text in texts for line in text.splitlines() if not _is_code_or_path(line)}
    return sorted(line for line in lines if raw_names_in(line, CODE_NAMES))


@pytest.mark.parametrize("old", [False, True], ids=["seed", "old stored version"])
def test_no_raw_names_on_any_tab(published_rulebook, old):
    version = _old_version(published_rulebook) if old else published_rulebook

    assert _raw_names(version) == []
