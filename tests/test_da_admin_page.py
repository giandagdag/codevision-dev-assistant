import ast
from pathlib import Path

from callbacks.screen_callbacks.da_admin_page_callbacks import (
    admin_content,
    developer_page_style,
)
from layouts import da_admin_page
from layouts.da_admin_page import (
    ADMIN_PATH,
    ADMIN_TABS,
    TAB_OVERVIEW,
    admin_page,
    build_view,
    charter_view,
    list_table,
    refusal_page,
)

SRC = Path(__file__).resolve().parents[1] / "src"
RETIRED = ("default_level", "max_level", "never_generate", "max_review_rounds")


def walk(node):
    """Every component in a Dash tree, parents first."""
    yield node
    children = getattr(node, "children", None)
    if children is None:
        return
    for child in children if isinstance(children, list | tuple) else [children]:
        if hasattr(child, "to_plotly_json"):
            yield from walk(child)
        elif isinstance(child, str):
            yield child


def all_text(node) -> str:
    parts = []
    for item in walk(node):
        parts.append(item if isinstance(item, str) else "")
        for prop in ("label", "value", "id"):
            value = getattr(item, prop, None)
            if value is not None and not isinstance(item, str):
                parts.append(str(value))
    return "\n".join(parts)


def test_the_console_has_8_tabs_with_overview_first(published_rulebook):
    page = admin_page(published_rulebook)

    tabs = next(c for c in walk(page) if type(c).__name__ == "Tabs")
    labels = [c.children for c in walk(tabs) if type(c).__name__ == "TabsTab"]
    assert len(labels) == 8
    assert labels[0] == "Overview"
    assert tabs.value == TAB_OVERVIEW
    assert [label for _, label, _ in ADMIN_TABS] == labels


def test_a_listed_admin_sees_the_console(make_settings, published_rulebook):
    settings = make_settings(admin_ids=("admin-0001",), developer_id="admin-0001")

    content = admin_content(settings, ADMIN_PATH)

    assert "Admin console" in all_text(content)


def test_anyone_else_sees_only_the_refusal(make_settings, published_rulebook):
    settings = make_settings(admin_ids=("admin-0001",), developer_id="dev-0002")

    text = all_text(admin_content(settings, ADMIN_PATH))

    assert "core team" in text
    assert "Project charter" not in text
    assert published_rulebook.rulebook.charter.purpose not in text


def test_an_empty_admin_list_lets_nobody_in(make_settings, published_rulebook):
    settings = make_settings(developer_id="admin-0001")

    assert "core team" in all_text(admin_content(settings, ADMIN_PATH))


def test_other_paths_show_no_admin_content_and_admin_hides_the_developer_page(make_settings):
    assert admin_content(make_settings(), "/") is None
    assert developer_page_style(ADMIN_PATH) == {"display": "none"}
    assert developer_page_style("/") == {}


def test_charter_view_shows_every_section_and_the_size_check(published_rulebook):
    text = all_text(charter_view(published_rulebook))

    for word in ("Purpose", "In scope", "Out of scope", "Architecture principles", "Constraints"):
        assert word in text
    assert "Glossary" in text
    assert "Charter size" in text
    assert published_rulebook.rulebook.charter.purpose in text


def test_build_view_shows_limits_with_bounds_and_advanced_collapsed(published_rulebook):
    view = build_view(published_rulebook)

    text = all_text(view)
    assert "Max fix rounds: 3   (allowed: 1 to 5)" in text
    assert "Advanced limits" in text
    accordion = next(c for c in walk(view) if type(c).__name__ == "Accordion")
    assert accordion.value is None  # collapsed
    for label in ("Generator model", "Tester model", "Flag-for-review zones", "Protected files"):
        assert label in text
    switches = [c for c in walk(view) if type(c).__name__ == "Switch"]
    assert len(switches) == 5


def test_no_screen_shows_a_retired_field(published_rulebook):
    for view in (
        admin_page(published_rulebook),
        charter_view(published_rulebook),
        build_view(published_rulebook),
    ):
        text = all_text(view).lower()
        for word in RETIRED:
            assert word not in text


def test_the_table_helper_adds_row_and_remove_only_in_edit_mode():
    rows = [{"term": "Batch", "meaning": "Jobs"}]

    read = all_text(list_table("charter", "t", ("term", "meaning"), rows, editable=False))
    edit = all_text(list_table("charter", "t", ("term", "meaning"), rows, editable=True))

    assert "Add row" not in read and "Remove" not in read
    assert "Add row" in edit and "Remove" in edit
    assert "Nothing here yet." in all_text(
        list_table("charter", "t", ("term",), [], editable=False)
    )


def test_admin_callbacks_import_nothing_from_the_developer_callbacks():
    path = SRC / "callbacks" / "screen_callbacks" / "da_admin_page_callbacks.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not [m for m in modules if "developer_assistant_page" in m]


def test_only_the_storage_file_writes_sql_against_the_rulebook_table():
    for file in _admin_files():
        assert "da_rulebook_versions" not in file.read_text(encoding="utf-8"), file
    assert da_admin_page.ADMIN_PATH == "/admin"


def _admin_files():
    for path in (SRC / "layouts", SRC / "callbacks", SRC / "agents"):
        yield from path.rglob("da_admin*.py")


def test_the_console_makes_no_ai_call():
    banned = ("get_llm_client", "get_build_client", "get_tester_client", ".complete(")
    for file in _admin_files():
        text = file.read_text(encoding="utf-8")
        for word in banned:
            assert word not in text, (file, word)


def test_refusal_page_builds():
    assert "core team" in all_text(refusal_page())
