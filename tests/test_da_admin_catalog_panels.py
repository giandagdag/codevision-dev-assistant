"""Fix G4 L1 to L4: even catalog rows, patterns side panel, Add modules pop-up."""

from agents.da_admin_forms import capability_rows
from agents.da_admin_modules import (
    add_modules_to_form,
    count_matches,
    edit_patterns,
    is_exact,
    module_rows,
)
from callbacks.screen_callbacks.da_admin_page_callbacks import (
    modules_table_for,
    pattern_hint,
    run_action,
)
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions
from layouts.da_admin_catalog_panels import hint_text, modules_table
from layouts.da_admin_catalog_tab import CATALOG_INPUT_HEIGHT, CATALOG_WIDTHS, catalog_view
from layouts.da_admin_common import pat_id
from pydantic_classes.da_rulebook_models import Capability
from tests.test_da_admin_catalog_screen import act
from tests.test_da_admin_page import all_text, walk

ADMIN = "admin-0001"
TAB = "capability"
PATHS = ["a/x.py", "a/y.py", "b/limits_one.py", "b/z.py"]


def cap(name, patterns):
    return Capability(
        name=name, description=f"{name} things", named_senior="Lead", path_patterns=patterns
    )


def test_pattern_helpers_count_and_edit():
    assert is_exact("a/x.py") and not is_exact("a/*.py")
    assert count_matches("a/*", PATHS) == 2
    form = {"capabilities": [{"name": "L", "path_patterns": "a/*\nb/z.py"}]}

    edit_patterns(form, 0, remove="a/*")
    edit_patterns(form, 0, add="  b/*limits*  ")
    edit_patterns(form, 0, add="")  # blank: ignored

    assert form["capabilities"][0]["path_patterns"] == "b/z.py\nb/*limits*"
    assert hint_text("a/*", PATHS) == "matches 2 modules: a/x.py, a/y.py"
    assert hint_text("zzz", PATHS).startswith("Matches nothing yet")
    assert hint_text("  ", PATHS) == ""


def test_add_modules_makes_exact_patterns_and_moves_from_the_other_capability():
    form = {
        "capabilities": [
            {"name": "A", "path_patterns": "a/x.py\nq/other.py"},
            {"name": "B", "path_patterns": "b/z.py"},
        ]
    }

    add_modules_to_form(form, "B", ["a/x.py", "a/y.py", "b/z.py"])

    assert form["capabilities"][0]["path_patterns"] == "q/other.py"
    assert form["capabilities"][1]["path_patterns"].splitlines() == ["b/z.py", "a/x.py", "a/y.py"]


def test_module_rows_filter_and_say_where_a_module_moves_from():
    caps = [cap("A", ["a/*"]), cap("B", ["b/z.py"])]
    summaries = {"b/limits_one.py": "Checks the limit"}

    unassigned = module_rows(caps, PATHS, summaries, target="B")
    everything = module_rows(caps, PATHS, summaries, target="B", unassigned_only=False)
    by_path = {r["path"]: r for r in everything}

    assert [r["path"] for r in unassigned] == ["b/limits_one.py"]
    assert by_path["a/x.py"]["moves_from"] == "A"
    assert by_path["b/z.py"]["moves_from"] == ""  # already in the target
    assert [r["path"] for r in module_rows(caps, PATHS, summaries, "B", "checks")] == [
        "b/limits_one.py"
    ]


def test_the_modules_table_shows_full_paths_and_moves_from():
    caps = [cap("A", ["a/*"])]
    long_path = "src/very/long/folder/name/that/must/not/be/cut/module.py"

    text = all_text(modules_table(caps, [*PATHS, long_path], {}, "B", unassigned_only=False))

    assert long_path in text
    assert "moves from A" in text


def test_the_edit_catalog_has_fixed_widths_one_height_chip_and_add_modules(published_rulebook):
    view = catalog_view(published_rulebook, editable=True, modules=PATHS)
    nodes = list(walk(view))
    first = capability_rows(published_rulebook.rulebook.policy)[0]
    count = len(first["path_patterns"].splitlines())

    assert "Browse modules..." in all_text(view) and "+ Add capability" in all_text(view)
    assert f"{count} pattern" in all_text(view)
    # L2: the first row's up and the last row's down are disabled; the others work.
    moves = [n for n in nodes if isinstance(getattr(n, "id", None), dict)
             and n.id.get("type") == "adm-move"]
    off = {(n.id["index"], n.id["step"]) for n in moves if n.disabled}
    assert off == {(0, -1), (len(moves) // 2 - 1, 1)}
    assert sum(int(v.rstrip("%")) for v in CATALOG_WIDTHS.values()) == 100
    heights = {
        n.styles["input"]["height"]
        for n in nodes
        if isinstance(getattr(n, "styles", None), dict) and "input" in n.styles
    }
    assert heights == {CATALOG_INPUT_HEIGHT}


def test_open_remove_add_and_save_in_the_patterns_panel_make_one_version(
    make_settings, published_rulebook
):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    before = len(list_versions(settings.db_path))
    version = get_active_version(settings.db_path)
    form = {"capabilities": capability_rows(version.rulebook.policy)}
    first = form["capabilities"][0]["path_patterns"].splitlines()[0]

    opened, editing = run_action(settings, TAB, pat_id(TAB, "open", 0), form, "", None, {})
    titles = [getattr(n, "title", "") for n in walk(opened)]  # the side panel's heading
    assert editing is True and any(str(t).startswith("Patterns:") for t in titles)
    assert first in all_text(opened)

    run_action(settings, TAB, pat_id(TAB, "remove", 0, first), form, "", None, {})
    run_action(settings, TAB, pat_id(TAB, "add", 0), form, "", None, {"newpat": "zz/new.py"})
    assert "zz/new.py" not in form["capabilities"][0]["path_patterns"]  # matches nothing: refused
    assert len(list_versions(settings.db_path)) == before  # nothing written yet

    _, editing = run_action(
        settings, TAB, pat_id(TAB, "force", 0), form, "Tidy patterns", None, {"newpat": "zz/new.py"}
    )

    assert editing is False
    assert len(list_versions(settings.db_path)) == before + 1
    saved = get_active_version(settings.db_path).rulebook.policy.capabilities[0]
    assert "zz/new.py" in saved.path_patterns and first not in saved.path_patterns


def test_add_modules_adds_three_exact_patterns_in_one_version(make_settings, published_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    before = len(list_versions(settings.db_path))
    version = get_active_version(settings.db_path)
    target = version.rulebook.policy.capabilities[0].name
    form = {"capabilities": capability_rows(version.rulebook.policy)}
    picked = ["m/one.py", "m/two.py", "m/three.py"]

    opened, _ = run_action(settings, TAB, pat_id(TAB, "openmods"), form, "", None, {})
    assert "Browse modules" in all_text(opened)
    content, _ = run_action(
        settings, TAB, pat_id(TAB, "addmods"), form, "", None, {"cap": target, "picked": picked}
    )
    assert len(list_versions(settings.db_path)) == before
    drafted = {
        n.id["col"]: n.value
        for n in walk(content)
        if isinstance(getattr(n, "id", None), dict)
        and n.id.get("type") == "adm-cell"
        and n.id["row"] == 0
    }
    assert all(p in drafted["path_patterns"] for p in picked)

    run_action(settings, TAB, act("save"), form, "Add three modules", None)

    saved = get_active_version(settings.db_path).rulebook.policy.capabilities[0]
    assert all(p in saved.path_patterns for p in picked)
    assert len(list_versions(settings.db_path)) == before + 1


def test_g6_7_also_add_here_keeps_the_other_capability(make_settings, published_rulebook):
    from agents.da_admin_modules import also_add_modules_to_form

    form = {"capabilities": [
        {"name": "Markdown", "path_patterns": "a/x.py"},
        {"name": "Ingestion", "path_patterns": "b/*.py"},
    ]}  # fmt: skip

    also_add_modules_to_form(form, "Ingestion", ["a/x.py"])

    assert form["capabilities"][0]["path_patterns"] == "a/x.py"
    assert form["capabilities"][1]["path_patterns"] == "b/*.py\na/x.py"


def test_the_pop_up_has_both_move_and_also_add_buttons(make_settings, published_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    version = get_active_version(settings.db_path)
    form = {"capabilities": capability_rows(version.rulebook.policy)}

    opened, _ = run_action(settings, TAB, pat_id(TAB, "openmods"), form, "", None, {})

    assert "Also add here" in all_text(opened)


def test_the_pop_up_stays_open_when_nothing_is_ticked(make_settings, published_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    version = get_active_version(settings.db_path)
    form = {"capabilities": capability_rows(version.rulebook.policy)}

    content, _ = run_action(
        settings, TAB, pat_id(TAB, "addmods"), form, "", None, {"cap": "", "picked": []}
    )

    assert "Add 0 modules" in all_text(content)


def test_live_hint_and_filter_functions(make_settings, published_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)

    assert pattern_hint(settings, "*").startswith("matches ")
    table = modules_table_for(settings, "", "", False, False, [], select_all=True)

    assert table.children[0].value  # every shown row ticked
