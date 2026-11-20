"""Fix G4 step 2: the thinking line on the Admin screens, in plain words (T1, T9, G4-19)."""

import dataclasses

import pytest

from agents.da_admin_overview import THINKING_LABEL, server_settings_view
from layouts.da_admin_build_tab import build_view
from tests.da_tree import all_text

pytestmark = pytest.mark.usefixtures("published_rulebook")


def test_server_settings_row_is_plain_words(make_settings):
    off = dataclasses.replace(make_settings(), onprem_thinking="off")

    row = dict(server_settings_view(off))[THINKING_LABEL]

    assert row == "off; temperature 0.2, top_p 0.2"
    assert "DA_" not in THINKING_LABEL + row
    assert "server default" in dict(server_settings_view(make_settings()))[THINKING_LABEL]


def test_build_tab_shows_one_read_only_thinking_line(make_settings, published_rulebook):
    server = server_settings_view(make_settings())

    shown = all_text(build_view(published_rulebook, server=server))

    assert "AI thinking: server default; temperature 0.2, top_p 0.2" in shown
    assert "DA_" not in shown
    assert "AI thinking" not in all_text(build_view(published_rulebook))
