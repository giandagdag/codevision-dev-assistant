"""F12 (B1-15): each waiting button has its own busy line."""

from layouts.da_busy_text import BUSY_JS, BUSY_LINES, busy_line


def test_b1_15_every_known_button_has_its_own_line():
    lines = list(BUSY_LINES.values())

    assert len(lines) == len(set(lines))  # no button shows another button's text


def test_b1_15_the_line_follows_the_label():
    assert busy_line("Upload folder to re-scan") == "⏳ Re-scanning your folder…"
    assert busy_line(" Proceed to Approach ") == "⏳ Asking the AI for an approach…"


def test_b1_15_an_unknown_button_gets_a_line_from_its_own_label():
    assert "Do the thing" in busy_line("Do the thing")


def test_b1_15_the_browser_script_carries_the_same_table():
    assert "Re-scanning your folder" in BUSY_JS and "da-busy" in BUSY_JS
