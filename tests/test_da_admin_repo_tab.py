"""Fix 11-1, L5 (step 24): Repository and index has a left and a right column, folders as chips."""

from layouts.da_admin_page import TAB_REPO, tab_content
from tests.test_da_admin_page import all_text, walk


def two_col_grid(content):
    return next(
        c for c in walk(content) if "gridTemplateColumns" in (getattr(c, "style", None) or {})
    )


def test_connection_is_on_the_left_and_index_health_on_the_right(published_rulebook):
    grid = two_col_grid(tab_content(TAB_REPO, published_rulebook, server=[]))

    left, right = grid.children
    assert "Connection" in all_text(left) and "Index health" not in all_text(left)
    assert "Index health" in all_text(right) and "Recent refreshes" in all_text(right)
    assert "Connection" not in all_text(right)


def test_read_view_shows_folders_and_markers_as_chips(published_rulebook):
    policy = published_rulebook.rulebook.policy
    view = tab_content(TAB_REPO, published_rulebook, server=[])

    chips = [c.children for c in walk(view) if type(c).__name__ == "Badge"]
    assert set(policy.allowed_folders) <= set(chips)
    assert set(policy.workspace_markers) <= set(chips)


def test_edit_view_keeps_the_folder_and_marker_tables(published_rulebook):
    view = tab_content(TAB_REPO, published_rulebook, editable=True, server=[])

    tables = {
        c.id["table"]
        for c in walk(view)
        if isinstance(getattr(c, "id", None), dict) and c.id.get("type") == "adm-cell"
    }
    assert {"allowed_folders", "workspace_markers"} <= tables
