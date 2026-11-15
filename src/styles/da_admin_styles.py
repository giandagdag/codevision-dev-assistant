"""Admin console colours (fix 11-1, section 2): the 14 Nov demo palette in one place.

Admin screens take every colour from here. NAVY and BLUE are the same values as da_styles.py.
"""

from styles.da_styles import BLUE, NAVY

GREEN = "#157F3B"
GREEN_LIGHT = "#E6F4EA"
AMBER = "#9A5B00"
AMBER_LIGHT = "#FFF3DF"
RED = "#B42318"
RED_LIGHT = "#FDECEA"
VIOLET = "#5B4BC4"
VIOLET_LIGHT = "#EFEDFB"
BLUE_LIGHT = "#EAF1FD"

# Status word -> (text colour, background), for pills.
PILL_COLOURS = {
    "green": (GREEN, GREEN_LIGHT),
    "amber": (AMBER, AMBER_LIGHT),
    "red": (RED, RED_LIGHT),
    "violet": (VIOLET, VIOLET_LIGHT),
    "blue": (BLUE, BLUE_LIGHT),
    "navy": (NAVY, BLUE_LIGHT),
}


def pill_style(name: str) -> dict:
    """Inline style for a status pill; an unknown word gets the blue pill."""
    text, background = PILL_COLOURS.get(name, PILL_COLOURS["blue"])
    return {"color": text, "backgroundColor": background}
