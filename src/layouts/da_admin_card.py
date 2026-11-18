"""The shared Admin card, page title and grid (fix 11-3, rules V1 to V4).

Every Admin tab draws its sections with these, so no tab puts loose text on the page background.
Styles come only from styles/da_admin_styles.py (V8).
"""

import dash_mantine_components as dmc
from dash import html

from styles import da_admin_styles as s
from styles import da_styles

TAB_PURPOSE = {
    "overview": "How healthy the rulebook, the index and the catalog are, and what needs you.",
    "charter": "What the Developer Assistant is for, what it must not do, and the words it uses.",
    "repo": "Which code the assistant reads, how it is refreshed, and the state of the index.",
    "capability": "The business capabilities the code is grouped into, and unassigned programs.",
    "ui": "The brand look and the screen conventions that generated code must follow.",
    "coding": "The coding rules that review and generated code are checked against.",
    "build": "How generated code is built and tested before a developer sees it.",
    "history": "Every published rulebook version: who, when, and why.",
}


def page_title(name: str, purpose: str) -> html.Div:
    """V1: the tab name (22 px) and one plain line saying what the tab is for."""
    return html.Div(
        [html.H2(name, style=s.PAGE_TITLE), dmc.Text(purpose, size="sm", c=da_styles.MUTED)],
        style=s.PAGE_TITLE_BOX,
    )


def admin_card(title: str, body, icon: str = "", count=None, actions=None, **extra) -> html.Div:
    """V2 and V3: a white card; header = icon tile, title, count pill, actions on the right."""
    header = [
        *([html.Span(icon, style=s.CARD_ICON)] if icon else []),
        html.Span(title, style=s.CARD_TITLE),
        *([dmc.Badge(str(count), variant="light", tt="none")] if count is not None else []),
        *([html.Div(actions)] if actions is not None else []),
    ]
    return html.Div(
        [html.Div(header, style=s.CARD_HEADER), body],
        className=s.CARD_CLASS,
        style={**s.CARD, **extra.pop("style", {})},
        **extra,
    )


def is_card(node) -> bool:
    return getattr(node, "className", None) == s.CARD_CLASS


def card_grid(main: list, side: list) -> html.Div:
    """V4: main column 2/3, side column 1/3, 16 px gaps. Both columns hold cards."""
    return html.Div(
        [html.Div(main, style=s.CARD_STACK), html.Div(side, style=s.CARD_STACK)], style=s.GRID
    )
