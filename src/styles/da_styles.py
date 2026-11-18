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
    # B2 S9: on a wide screen the extra width goes to the right panel; the chat stays readable.
    "gridTemplateColumns": "minmax(380px, 1fr) minmax(0, 1.5fr)",
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

BUBBLE_BASE = {"maxWidth": "min(88%, 80ch)", "whiteSpace": "pre-wrap", "wordBreak": "break-word"}
BUBBLE = {
    "developer": {**BUBBLE_BASE, "alignSelf": "flex-end", "background": BLUE, "color": "white"},
    "assistant": {**BUBBLE_BASE, "alignSelf": "flex-start", "background": CANVAS, "color": INK},
    "system": {**BUBBLE_BASE, "alignSelf": "center", "background": BLUE_LIGHT, "color": INK},
}
# A line from a senior (Phase 10): left side like the assistant, but amber with a border.
BUBBLE_SENIOR = {
    **BUBBLE_BASE, "alignSelf": "flex-start", "background": AMBER_LIGHT, "color": INK,
    "border": "1px solid #E8C16F",
}  # fmt: skip

# Help and escalation buttons (P21): outlined, so they read as clickable but less prominent than the
# main blue buttons. Only the border colour is set here: the Mantine "default" variant already gives
# white background and dark text, and a disabled button keeps Mantine's own greyed-out look.
SECONDARY_BUTTON_BORDER = {"borderColor": "#7C879B"}

CHOICES_BAR = {"padding": "12px 16px 0", "borderTop": f"1px solid {LINE}"}
COMPOSER = {"padding": "12px 16px", "borderTop": f"1px solid {LINE}"}

# The scroll box of a right-panel tab. minHeight 0 lets it shrink below its content, which is what
# makes the scroll bar appear instead of the panel growing past the window.
PANEL_BODY = {"flex": 1, "minHeight": 0, "overflow": "auto", "padding": "14px 18px 18px"}
# The Mantine tab panel that holds a PANEL_BODY: it takes the height left under the tab row, so
# the box inside is limited to it. Without this the panel grows with its content and never scrolls.
TAB_PANEL = {"flex": 1, "minHeight": 0, "display": "flex", "flexDirection": "column"}
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

# B2 S9: no fixed cap, the page uses the whole window width.
PAGE = {"width": "100%", "padding": "20px 28px"}
