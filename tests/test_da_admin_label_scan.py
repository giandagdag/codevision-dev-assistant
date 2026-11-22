"""AF-2: no raw field or setting names (DA_..., build_max_rounds) in the text the Admin draws."""

import pytest

from agents.da_admin_diff import build_timeline, diff_rulebooks, plain_diff_lines
from agents.da_admin_labels import raw_names_in
from agents.da_admin_metrics import health_report
from agents.da_admin_overview import build_overview
from db_table_functions.db_tbl_da_rulebook import get_active_version, get_version, save_new_version
from layouts.da_admin_page import ADMIN_TABS, admin_page, history_view, overview_view, tab_content
from pydantic_classes.da_rulebook_models import Rulebook

NEW_POLICY_FIELDS = (
    "index_repo", "index_branch", "index_folder_scope", "index_refresh_mode", "index_exclusions",
)
TEXT_PROPS = ("label", "title", "description", "placeholder")
# Folder and library names that rules name on purpose: they are the thing, not a setting.
CODE_NAMES = frozenset(
    {"db_table_functions", "pydantic_classes", "dash_iconify", "dash_mantine_components"}
)


# Golden example code, rule examples and paths live in Code boxes. An outline Badge is a module
# chip. A light Badge is a status or severity pill: its words are scanned like any other text.
CODE_CHIPS = ("Code", "CodeHighlight")


def _is_code_chip(node) -> bool:
    name = type(node).__name__
    return name in CODE_CHIPS or (name == "Badge" and getattr(node, "variant", None) == "outline")


def _words(node):
    """Like walk(), but never goes inside a code chip: those may hold raw names on purpose."""
    yield node
    if _is_code_chip(node):
        return
    children = getattr(node, "children", None)
    if children is None:
        return
    for child in children if isinstance(children, list | tuple) else [children]:
        if hasattr(child, "to_plotly_json"):
            yield from _words(child)
        elif isinstance(child, str):
            yield child


def shown_text(node) -> str:
    """Only words a person reads: text children and the label-like props, never component ids."""
    parts = []
    for item in _words(node):
        if isinstance(item, str):
            parts.append(item)
            continue
        if _is_code_chip(item):
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


def _saved_second_version(settings, version):
    """Save v2 (rounds changed) so History has two versions and a real compare to draw."""
    policy = version.rulebook.policy.model_copy(update={"build_max_rounds": 4})
    save_new_version(
        settings.db_path, version.rulebook.model_copy(update={"policy": policy}), 1, "admin-0001",
        "Rounds four",
    )


def _overview_and_history(settings):
    """The two tabs that need stored data: Overview (areas, attention, health) and History."""
    overview = build_overview(settings)
    active = get_active_version(settings.db_path)
    drawn = [overview_view(active, overview, health_report(settings.db_path))]
    rows = build_timeline(settings.db_path)
    old, new = (get_version(settings.db_path, n).rulebook for n in (1, 2))
    drawn.append(history_view(
        rows, selected=2, selected_changes=plain_diff_lines(diff_rulebooks(old, new)),
    ))
    return drawn


def _raw_names(version, stored_tabs) -> list[str]:
    """The drawn lines that hold a raw name (the whole line, so a failure shows where)."""
    texts = [shown_text(admin_page(version))]
    for tab, _, _ in ADMIN_TABS:
        if tab not in ("overview", "history"):
            texts.append(shown_text(tab_content(tab, version, editable=True)))
    texts += [shown_text(tab) for tab in stored_tabs]
    lines = {line for text in texts for line in text.splitlines()}
    return sorted(line for line in lines if raw_names_in(line, CODE_NAMES))


@pytest.mark.parametrize("old", [False, True], ids=["seed", "old stored version"])
def test_no_raw_names_on_any_tab(make_settings, published_rulebook, old):
    settings = make_settings(admin_ids=("admin-0001",), developer_id="admin-0001")
    _saved_second_version(settings, published_rulebook)
    version = _old_version(published_rulebook) if old else published_rulebook

    assert _raw_names(version, _overview_and_history(settings)) == []


def test_fix2_new_parts_show_no_raw_names():
    """AG-15: the AI scan cards, the confirm box and the meaning results use plain words."""
    from agents.da_admin_meaning import FROM_CODE, ModuleHit
    from agents.da_admin_tag_cards import AiCard
    from layouts.da_admin_catalog_meaning import meaning_results, no_hits_line
    from layouts.da_admin_catalog_tab import queue_block

    cards = [
        AiCard("src/agents/docs_folder_to_md.py", "Documents", "high", "Writes markdown", "fits"),
        AiCard("src/agents/odd_tool.py", "", "low", "Unclear", "none fits"),
    ]
    queue = {
        "rows": [], "resolved": None, "dialog": None, "notice": [],
        "ai_cards": cards, "ai_confirm": {"counts": {"Documents": 1}},
    }
    path = "src/agents/docs_folder_to_md.py"
    hit = ModuleHit(path, ("convert",), "Documents", "Writes", FROM_CODE, 1.0)
    parts = [
        queue_block(queue, ["Documents"]), meaning_results([hit]), meaning_results([], "x"),
        no_hits_line(),
    ]
    text = "\n".join(shown_text(p) for p in parts)
    # A module path on a result button is the program itself, like a code chip: skip exact paths.
    lines = [ln for ln in text.splitlines() if ln != path]
    assert not [ln for ln in lines if raw_names_in(ln, CODE_NAMES)]


def test_g4_new_screen_parts_show_no_raw_names(published_rulebook):
    """G4-19: the Review queue, bulk bar, patterns panel, Add modules pop-up and charter."""
    from agents.da_admin_review import ReviewFilter, bulk_plan
    from agents.da_admin_tag_cards import AiCard
    from layouts.da_admin_catalog_panels import modules_modal, patterns_panel
    from layouts.da_admin_page import charter_view
    from layouts.da_admin_review_view import bulk_bar, bulk_confirm, review_pane

    cards = [AiCard("src/agents/docs_folder_to_md.py", "Documents", "high", "Writes", "fits")]
    caps = published_rulebook.rulebook.policy.capabilities
    names = [c.name for c in caps]
    path = cards[0].path
    plan = bulk_plan([path], cards)
    parts = [
        review_pane(ReviewFilter(), ["src"], 1, 1, [], [], bulk_bar([path], cards, names)),
        bulk_confirm("approve", plan, 1, ""), bulk_confirm("reject", plan, 1, ""),
        patterns_panel("capability", 0, names[0], "src/agents/*limits*", [path]),
        modules_modal("capability", caps, [path], {}, ""),
        charter_view(published_rulebook, editable=True),
    ]
    lines = [ln for p in parts for ln in shown_text(p).splitlines() if ln != path]
    assert not [ln for ln in lines if raw_names_in(ln, CODE_NAMES)]


def test_g5_25_catalog_look_parts_show_no_raw_names(published_rulebook):
    """G5-25: the catalog edit view (Browse modules button, arrows, tooltips) and both panels."""
    from layouts.da_admin_catalog_panels import modules_modal, patterns_panel
    from layouts.da_admin_catalog_tab import catalog_view

    caps = published_rulebook.rulebook.policy.capabilities
    paths = ["agent_flows/da_scan.py"]
    parts = [
        catalog_view(published_rulebook, editable=True, modules=paths),
        patterns_panel("capability", 0, caps[0].name, "agent_flows/*", paths),
        patterns_panel("capability", 0, caps[0].name, "nothing/*", paths),
        modules_modal("capability", caps, paths, {}, ""),
    ]
    # Paths and the example pattern (a real folder from the index, G5 L3) are the thing itself.
    skip = {*paths, "agent_flows/*"}
    lines = [ln for p in parts for ln in shown_text(p).splitlines() if ln not in skip]
    assert not [ln for ln in lines if raw_names_in(ln, CODE_NAMES)]
