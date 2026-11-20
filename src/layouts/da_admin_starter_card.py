"""The starter-data pieces on Repository and index and on the Capability catalog (Fix G4, C2)."""

import dash_mantine_components as dmc

from agents.da_admin_starter import ACTION_ALL, ACTION_ONE, SCOPE_TEXT, Leftover
from layouts.da_admin_card import admin_card
from layouts.da_admin_common import TAB_CAPABILITY, TAB_REPO, act_id

CLEAR_LABEL = "Clear and use CodeVision's folder"
CARD_TITLE = "From the starter list (made-up, not CodeVision)"
REMOVE_ALL_LABEL = "Remove all starter items"


def _what(item: Leftover) -> str:
    if item.kind == "scope":
        return f"Folder scope: {item.text}"
    if item.kind == "capability":
        return f"Capability: {item.text}"
    return f"Pattern '{item.text}' in {item.capability}"


def scope_alert(leftovers: list[Leftover]):
    """The red box on the Connection card, or nothing when the scope is fine."""
    position = next((i for i, x in enumerate(leftovers) if x.kind == "scope"), None)
    if position is None:
        return None
    return dmc.Alert(
        dmc.Group(
            [
                dmc.Text(SCOPE_TEXT, size="sm"),
                dmc.Button(
                    CLEAR_LABEL,
                    id=act_id(TAB_REPO, f"{ACTION_ONE}{position}"),
                    size="compact-xs",
                    color="red",
                ),
            ]
        ),
        color="red",
    )


def starter_card(leftovers: list[Leftover]):
    """A card above the catalog: each leftover as a row with Remove, and Remove all."""
    if not leftovers:
        return None
    rows = [
        dmc.Group(
            [
                dmc.Text(_what(item), size="sm"),
                dmc.Button(
                    "Remove",
                    id=act_id(TAB_CAPABILITY, f"{ACTION_ONE}{i}"),
                    size="compact-xs",
                    variant="light",
                ),
            ],
            justify="space-between",
        )
        for i, item in enumerate(leftovers)
    ]
    rows.append(
        dmc.Button(REMOVE_ALL_LABEL, id=act_id(TAB_CAPABILITY, ACTION_ALL), color="red", size="xs")
    )
    return admin_card(CARD_TITLE, dmc.Stack(rows, gap="xs"), "⚠", count=len(leftovers))
