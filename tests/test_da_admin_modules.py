"""Fix 11-1 step 8 (AF-9, AF-5): module chips per capability, search, Missing backup, Add module."""

from agents.da_admin_modules import (
    SHOWN_MODULES,
    matches_search,
    module_chips,
    module_paths,
    modules_by_capability,
    share_counts,
)
from callbacks.screen_callbacks.da_admin_page_callbacks import (
    filtered_catalog,
    with_added_module,
)
from layouts.da_admin_page import (
    CAP_MISSING_ID,
    CAP_SEARCH_ID,
    catalog_list,
    catalog_view,
)
from pydantic_classes.da_rulebook_models import Capability
from tests.test_da_admin_page import all_text, walk

SCOPE = "src/data/da_fake_codevision"


def cap(name, patterns, backup="Deputy"):
    return Capability(
        name=name,
        description=f"{name} things",
        named_senior="Lead",
        backup_senior=backup,
        path_patterns=patterns,
    )


def test_home_modules_come_from_the_files_under_the_folder_scope(tmp_path):
    paths = module_paths(SCOPE, index_dir=tmp_path)  # no index file there

    assert "src/agents/limits_expiry_report.py" in paths


def test_a_built_index_wins_over_the_files(tmp_path):
    (tmp_path / "da_code_index.json").write_text(
        '{"pieces": [{"path": "a/x.py"}, {"path": "a/x.py"}, {"path": "b/y.py"}]}',
        encoding="utf-8",
    )

    assert module_paths(SCOPE, index_dir=tmp_path) == ["a/x.py", "b/y.py"]


def test_a_shared_module_shows_x2_under_both_capabilities():
    caps = [cap("Limits", ["*limits*"]), cap("Reports", ["*report*"])]
    paths = ["src/limits_expiry_report.py", "src/limits_menu.py"]

    by_cap = modules_by_capability(caps, paths)
    counts = share_counts(by_cap)

    assert by_cap["Limits"] == paths
    assert by_cap["Reports"] == ["src/limits_expiry_report.py"]
    assert module_chips(by_cap["Reports"], counts) == (["limits_expiry_report.py ×2"], 0)
    assert module_chips(by_cap["Limits"], counts)[0][1] == "limits_menu.py"


def test_chips_stop_at_six_then_plus_n_more():
    paths = [f"m/f{i}.py" for i in range(9)]

    labels, more = module_chips(paths, {})

    assert len(labels) == SHOWN_MODULES == 6
    assert more == 3
    view = catalog_list([cap("Big", ["m/*"])], paths)
    assert "+3 more" in all_text(view)


def test_search_matches_name_description_or_module_name():
    assert matches_search("Limits", "Customer limits", ["a/menu.py"], "menu")
    assert matches_search("Limits", "Customer limits", [], "customer")
    assert not matches_search("Limits", "Customer limits", ["a/menu.py"], "zzz")
    view = catalog_list([cap("Limits", ["*menu*"]), cap("Other", ["*x*"])], ["a/menu.py"], "menu")
    text = all_text(view)
    assert "Limits" in text
    assert "Other" not in text


def test_missing_backup_chip_filters_to_capabilities_without_a_backup():
    caps = [cap("Has", ["a*"]), cap("Lacks", ["b*"], backup="")]

    text = all_text(catalog_list(caps, [], missing_backup=True))

    assert "Lacks" in text
    assert "Has" not in text


def test_the_catalog_read_view_has_search_and_chip_and_edit_view_has_the_picker(
    published_rulebook,
):
    read = catalog_view(published_rulebook, modules=["a/x.py"])
    # Fix G4 L3: the picker is the "Add modules" pop-up, opened through the panel state.
    edit = catalog_view(
        published_rulebook, editable=True, modules=["a/x.py"], panel={"kind": "modules"}
    )

    read_ids = [getattr(c, "id", None) for c in walk(read)]
    assert CAP_SEARCH_ID in read_ids and CAP_MISSING_ID in read_ids
    assert "modules to" in all_text(edit)
    assert CAP_SEARCH_ID not in [getattr(c, "id", None) for c in walk(edit)]


def test_add_module_appends_an_exact_pattern_to_the_picked_capability():
    form = {
        "capabilities": [{"name": "Limits", "path_patterns": "*limits*"}],
        "capmodule": [{"capability": "Limits", "path": "src/x.py"}],
    }

    result = with_added_module(form)

    assert result["capabilities"][0]["path_patterns"] == "*limits*\nsrc/x.py"
    assert "capmodule" not in result


def test_add_module_with_no_pick_changes_nothing():
    form = {
        "capabilities": [{"name": "Limits", "path_patterns": "*limits*"}],
        "capmodule": [{"capability": "", "path": ""}],
    }

    assert with_added_module(form)["capabilities"][0]["path_patterns"] == "*limits*"


def test_the_filter_callback_function_draws_the_list(make_settings, published_rulebook):
    settings = make_settings(admin_ids=("admin-0001",), developer_id="admin-0001")

    text = all_text(filtered_catalog(settings, "limits", False))

    assert "Limits" in text
