"""Style values for the Developer Assistant screen (the cv_styles.py pattern: plain dicts).

Colours come from the concept demo. Real UOB fonts and colours are applied at work.
"""

NAVY = "#1E2B45"
BLUE = "#1F6FE0"
BLUE_LIGHT = "#EAF1FD"
INK = "#2B3445"
MUTED = "#6B7385"
LINE = "#E3E7EE"
CANVAS = "#F6F8FB"
AMBER_LIGHT = "#FFF3DF"
HIGHLIGHT = "#FFF1C2"

CARD = {"border": f"1px solid {LINE}", "background": "white"}

# The whole workspace: chat on the left, panel on the right.
WORKSPACE_GRID = {
    "display": "grid",
    "gridTemplateColumns": "1fr 1fr",
    "gap": "16px",
    "height": "calc(100vh - 230px)",
    "minHeight": "460px",
}

COLUMN = {"display": "flex", "flexDirection": "column", "minHeight": 0, "overflow": "hidden"}

# column-reverse keeps the scroll at the newest message without any JavaScript.
CHAT_SCROLL = {
    "flex": 1,
    "overflow": "auto",
    "display": "flex",
    "flexDirection": "column-reverse",
}
CHAT_MESSAGES = {"display": "flex", "flexDirection": "column", "gap": "12px", "padding": "16px"}

BUBBLE_BASE = {"maxWidth": "88%", "whiteSpace": "pre-wrap", "wordBreak": "break-word"}
BUBBLE = {
    "developer": {**BUBBLE_BASE, "alignSelf": "flex-end", "background": BLUE, "color": "white"},
    "assistant": {**BUBBLE_BASE, "alignSelf": "flex-start", "background": CANVAS, "color": INK},
    "system": {**BUBBLE_BASE, "alignSelf": "center", "background": BLUE_LIGHT, "color": INK},
}

CHOICES_BAR = {"padding": "12px 16px 0", "borderTop": f"1px solid {LINE}"}
COMPOSER = {"padding": "12px 16px", "borderTop": f"1px solid {LINE}"}

PANEL_BODY = {"flex": 1, "overflow": "auto", "padding": "14px 18px 18px"}
PANEL_SECTION = {"padding": "10px 0", "borderBottom": f"1px solid {LINE}"}
FIELD = {"padding": "4px 6px", "margin": "0 -6px", "borderRadius": "6px"}
FIELD_CHANGED = {**FIELD, "background": HIGHLIGHT}
EMPTY_TEXT = {"color": "#A8AFBC", "fontStyle": "italic", "fontSize": "13px"}

PROGRESS_SEGMENT = {"height": "6px", "borderRadius": "3px"}
SEGMENT_OFF = "#E6E9EF"
SEGMENT_WARN = "#E3A23B"

STEPPER = {"display": "flex", "gap": "6px", "alignItems": "center", "flexWrap": "wrap"}
STEP_CURRENT = {"background": BLUE_LIGHT, "color": BLUE, "fontWeight": 600}
STEP_OTHER = {"color": MUTED}
STEP_PILL = {"display": "flex", "gap": "8px", "alignItems": "center", "borderRadius": "999px"}

PAGE = {"maxWidth": "1400px", "margin": "0 auto", "padding": "20px 28px"}
