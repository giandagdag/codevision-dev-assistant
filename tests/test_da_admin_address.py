"""Fix G5 N5: the address words map to tab and view ids; bad words fall back to Overview."""

from layouts.da_admin_address import tab_and_view


def test_keys_map_to_tabs_and_views():
    assert tab_and_view("?tab=repository") == ("repo", None)
    assert tab_and_view("?tab=catalog&view=queue") == ("capability", "queue")
    assert tab_and_view("?tab=catalog&view=capabilities") == ("capability", "caps")
    assert tab_and_view("?tab=history") == ("history", None)


def test_plain_missing_or_bad_address_opens_overview():
    for search in (None, "", "?", "?tab=nope", "?view=queue"):
        assert tab_and_view(search) == ("overview", None)


def test_view_only_counts_on_the_catalog_tab():
    assert tab_and_view("?tab=build&view=queue") == ("build", None)
