"""Fix 11-1, AF-4 and AF-5 (jump part): Overview rows with icon and chips, jump buttons, tiles."""

from agents.da_admin_overview import MISSING_BACKUP_FILTER, attention_items, build_overview
from layouts.da_admin_page import TAB_CAPABILITY, _attention_list, overview_view
from tests.test_da_admin_page import all_text, walk

ADMIN = "admin-0001"


def _view(make_settings, published_rulebook, report):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    overview = build_overview(settings)
    return overview, overview_view(published_rulebook, overview, report)


def _report(make_settings):
    from agents.da_admin_metrics import health_report

    return health_report(make_settings().db_path)


def test_six_area_rows_each_link_to_their_tab_with_chips_and_a_pill(
    make_settings, published_rulebook
):
    overview, view = _view(make_settings, published_rulebook, _report(make_settings))

    body = next(c for c in walk(view) if type(c).__name__ == "TableTbody")
    assert len(body.children) == 6
    tabs = set()
    for row in body.children:
        nodes = list(walk(row))
        assert any(type(c).__name__ == "Badge" and c.variant == "light" for c in nodes)
        assert any(type(c).__name__ == "Badge" and c.variant == "outline" for c in nodes)
        link = next(c for c in nodes if type(c).__name__ == "Button")
        tabs.add(link.id["tab"])
    assert len(tabs) == 6


def test_status_pills_in_the_rows_are_never_clipped(make_settings, published_rulebook):
    _, view = _view(make_settings, published_rulebook, _report(make_settings))

    body = next(c for c in walk(view) if type(c).__name__ == "TableTbody")
    pills = [
        c
        for row in body.children
        for c in walk(row)
        if type(c).__name__ == "Badge" and c.variant == "light" and c.style.get("width")
    ]
    assert len(pills) == 6
    for pill in pills:
        assert pill.style["width"] == "max-content" and pill.style["maxWidth"] == "none"
        assert pill.styles["label"]["textOverflow"] == "clip"


def test_the_missing_backup_line_has_an_assign_button_that_carries_tab_and_filter(
    make_settings, published_rulebook
):
    rulebook = published_rulebook.rulebook
    capability = rulebook.policy.capabilities[0].model_copy(update={"backup_senior": ""})
    policy = rulebook.policy.model_copy(update={"capabilities": [capability]})
    items = attention_items(rulebook.model_copy(update={"policy": policy}), [])

    item = next((i for i in items if i.filter), None)
    assert item is not None and item.filter == MISSING_BACKUP_FILTER
    assign = [c for c in walk(_attention_list(items)) if getattr(c, "children", None) == "Assign"]
    assert assign and assign[0].id["tab"] == TAB_CAPABILITY
    assert str(assign[0].id["n"]).startswith(MISSING_BACKUP_FILTER)


def test_health_numbers_are_tiles_and_keep_handoffs_and_escalations(
    make_settings, published_rulebook
):
    _, view = _view(make_settings, published_rulebook, _report(make_settings))

    papers = [c for c in walk(view) if type(c).__name__ == "Paper"]
    text = all_text(view)
    assert len(papers) >= 10
    assert "Handoffs: No data yet" in text and "Escalations: No data yet" in text
    window = next(c for c in walk(view) if type(c).__name__ == "SegmentedControl")
    assert [d["label"] for d in window.data] == ["Last 30 days", "All time"]


def test_section_15_health_numbers_are_a_full_width_row_under_the_two_columns(
    make_settings, published_rulebook
):
    """Gian, 16 Nov: no empty space at the lower left; the tiles run across the page."""
    from layouts.da_admin_overview_tab import HEALTH_ID, HEALTH_ROW_ID

    _, view = _view(make_settings, published_rulebook, _report(make_settings))

    top = view.children
    assert getattr(top[-1], "id", None) == HEALTH_ROW_ID  # last, under the two columns
    row_ids = [getattr(c, "id", None) for c in walk(top[-2])]
    assert HEALTH_ID not in row_ids  # not inside the right column any more
    grid = next(c for c in walk(top[-1]) if type(c).__name__ == "SimpleGrid")
    assert grid.cols["lg"] == 5
    assert "Needs attention" in all_text(top[-2])
