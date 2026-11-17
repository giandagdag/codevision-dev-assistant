"""Catalog search by meaning (fix 11-2, section 2): the mode switch and the results list.

Each result is a program with its capability, up to three function names and a one-line summary.
Clicking one filters the catalog table to the capability that holds it.
"""

import dash_mantine_components as dmc

from agents.da_admin_meaning import FROM_SUMMARY, ModuleHit
from styles import da_styles

CAP_MODE_ID = "adm-cat-mode"
CAP_MEANING_ID = "adm-cat-meaning"
HIT_TYPE = "adm-cat-hit"
MODE_NAMES, MODE_MEANING = "names", "meaning"
MODES = (
    {"value": MODE_NAMES, "label": "Names and people"},
    {"value": MODE_MEANING, "label": "What the code does"},
)
NAMES_PLACEHOLDER = "Search capability, module, senior or backup"
MEANING_PLACEHOLDER = "Describe what the code does, for example: creates markdown"
NO_HITS ="No program matches that description."


def mode_switch(value: str = MODE_NAMES):
    return dmc.SegmentedControl(id=CAP_MODE_ID, data=list(MODES), value=value, size="xs")


def meaning_results(hits: list[ModuleHit], message: str = ""):
    """The results list, a plain line when there is no index, or nothing before the first search."""
    if message:
        return dmc.Text(message, size="sm", style=da_styles.EMPTY_TEXT)
    if not hits:
        return None
    return dmc.Stack([_hit(h) for h in hits], gap="xs", mb="xs")


def no_hits_line():
    return dmc.Text(NO_HITS, size="sm", style=da_styles.EMPTY_TEXT)


def _hit(hit: ModuleHit):
    symbols = ", ".join(hit.symbols)
    return dmc.Paper(
        [
            dmc.Group(
                [
                    dmc.Button(
                        hit.path,
                        id={"type": HIT_TYPE, "path": hit.path},
                        variant="subtle",
                        size="compact-sm",
                        tt="none",
                    ),
                    dmc.Badge(hit.capability, variant="light", tt="none"),
                    dmc.Text("from summary" if hit.source == FROM_SUMMARY else "", size="xs",
                             c=da_styles.MUTED),  # fmt: skip
                ],
                gap="xs",
            ),
            dmc.Text(hit.summary, size="sm") if hit.summary else None,
            dmc.Text(symbols, size="xs", c=da_styles.MUTED) if symbols else None,
        ],
        withBorder=True,
        p="xs",
    )
