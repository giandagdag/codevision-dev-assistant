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


# Shared card (fix 3, V2 to V4): white, 1 px border, 12 px corners, 20 px padding, soft shadow.
CARD_CLASS = "da-admin-card"
CARD = {
    "background": "#FFFFFF",
    "border": "1px solid #E3E7EE",
    "borderRadius": "12px",
    "padding": "20px",
    "boxShadow": "0 1px 3px rgba(30, 43, 69, 0.08)",
    "minWidth": 0,
}
CARD_HEADER = {"display": "flex", "alignItems": "center", "gap": "10px", "marginBottom": "12px"}
CARD_ICON = {
    "width": "28px",
    "height": "28px",
    "borderRadius": "8px",
    "background": BLUE_LIGHT,
    "color": BLUE,
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "center",
    "fontSize": "14px",
}
CARD_TITLE = {"fontSize": "16px", "fontWeight": 600, "color": NAVY, "flex": 1}
PAGE_TITLE = {"fontSize": "22px", "fontWeight": 600, "color": NAVY, "margin": 0}
PAGE_TITLE_BOX = {"margin": "4px 0 16px"}
# Main column 2/3, side column 1/3, 16 px gaps (V4).
GRID = {
    "display": "grid",
    "gridTemplateColumns": "minmax(0, 2fr) minmax(0, 1fr)",
    "gap": "16px",
    "alignItems": "start",
}
# A list row: thin divider underneath (V5).
ROW = {"padding": "8px 0", "borderBottom": "1px solid #E3E7EE"}
CARD_STACK ={"display": "flex", "flexDirection": "column", "gap": "16px", "minWidth": 0}


def pill_style(name: str) -> dict:
    """Inline style for a status pill; an unknown word gets the blue pill."""
    text, background = PILL_COLOURS.get(name, PILL_COLOURS["blue"])
    return {"color": text, "backgroundColor": background}
