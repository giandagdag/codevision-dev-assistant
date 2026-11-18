"""Catalog search by meaning (fix 11-2, fix 11-3 D-E): the results under the one search box.

Each result is a program with its capability, up to three function names and a one-line summary.
Clicking one filters the catalog table to the capability that holds it.
"""

import dash_mantine_components as dmc

from agents.da_admin_meaning import FROM_SUMMARY, ModuleHit
from styles import da_styles

CAP_MEANING_ID = "adm-cat-meaning"
HIT_TYPE = "adm-cat-hit"
SEARCH_PLACEHOLDER = "Search capability, program, person, or what the code does"
MEANING_LABEL = "Matches what the code does"
NO_HITS = "No program matches that description."


def meaning_results(hits: list[ModuleHit], message: str = ""):
    """The results list, a plain line when there is no index, or nothing before the first search."""
    if message:
        return dmc.Text(message, size="sm", style=da_styles.EMPTY_TEXT)
    if not hits:
        return None
    label = dmc.Text(MEANING_LABEL, size="xs", fw=600, c=da_styles.MUTED)
    return dmc.Stack([label, *[_hit(h) for h in hits]], gap="xs", mb="xs")


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
