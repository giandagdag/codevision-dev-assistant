"""The Review queue's own space (Fix G4 L7 to L10): control bar, scrolling list box, bulk bar.

The cards themselves are drawn by da_admin_catalog_tab; this file draws what is around them.
Styles live in styles/da_admin_styles.py.
"""

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_review import (
    CONFIDENCES,
    NO_MATCH,
    PROPOSALS,
    SORTS,
    SOURCES,
    BulkPlan,
    ReviewFilter,
    bulk_plan,
    count_line,
)
from layouts.da_admin_queue_ids import (
    BULK_APPROVE,
    BULK_ASSIGN,
    BULK_PICK_UID,
    BULK_REJECT,
    Q_BULK_ASK,
    Q_BULK_DO,
    Q_CANCEL,
    Q_CLEAR_FILTERS,
    Q_SELECT_ALL,
    QUEUE_PICK_TYPE,
    RQ_BAR_ID,
    RQ_CONF_ID,
    RQ_COUNT_ID,
    RQ_FOLDER_ID,
    RQ_LIST_ID,
    RQ_PROPOSAL_ID,
    RQ_SEARCH_ID,
    RQ_SORT_ID,
    RQ_SOURCE_ID,
    queue_button_id,
)
from styles import da_admin_styles as admin_styles
from styles import da_styles


def _chips(component_id: str, label: str, options: dict[str, str], chosen: tuple[str, ...]):
    """A row of filter chips (several can be on). `options` is value to words."""
    return dmc.Group(
        [
            dmc.Text(label, size="xs", fw=600, c=da_styles.MUTED),
            dmc.ChipGroup(
                dmc.Group(
                    [dmc.Chip(words, value=value, size="xs") for value, words in options.items()],
                    gap=4,
                ),
                id=component_id,
                multiple=True,
                value=list(chosen),
            ),
        ],
        gap="xs",
    )


def control_bar(rf: ReviewFilter, folders: list[str]):
    """Search, filter chips and sort. It sits above the list box, so it stays while that scrolls."""
    folder_options = {name: name for name in folders}
    return html.Div(
        [
            dmc.Group(
                [
                    dmc.TextInput(
                        id=RQ_SEARCH_ID,
                        value=rf.search,
                        placeholder="Search path or AI summary",
                        size="xs",
                        w=320,
                    ),
                    dmc.Select(
                        id=RQ_SORT_ID, data=[{"value": k, "label": v} for k, v in SORTS.items()],
                        value=rf.sort, size="xs", w=210, allowDeselect=False,
                    ),
                ],
                gap="xs",
                mb=4,
                style={"flexBasis": "100%"},  # search row alone on top, chip rows wrap beside
            ),
            _chips(RQ_SOURCE_ID, "Source", SOURCES, rf.source),
            _chips(RQ_PROPOSAL_ID, "Proposal", PROPOSALS, rf.proposal),
            _chips(RQ_CONF_ID, "Confidence", {c: c for c in CONFIDENCES}, rf.confidence),
            _chips(RQ_FOLDER_ID, "Folder", folder_options, rf.folder),
        ],
        style={"display": "flex", "flexWrap": "wrap", "gap": "4px 24px", "marginBottom": "8px"},
    )


def count_row(shown: int, total: int, disabled: bool = False):
    """"Showing 12 of 91", Select all shown, and Clear filters."""
    return dmc.Group(
        [
            dmc.Text(count_line(shown, total), id=RQ_COUNT_ID, size="xs", c=da_styles.MUTED),
            dmc.Button(
                "Select all shown", id=queue_button_id(Q_SELECT_ALL), size="compact-xs",
                variant="subtle", disabled=disabled,
            ),
            dmc.Button(
                "Clear filters", id=queue_button_id(Q_CLEAR_FILTERS), size="compact-xs",
                variant="subtle", disabled=disabled,
            ),
        ],
        gap="xs",
        mb=4,
    )


def empty_list():
    return html.Div(
        [
            dmc.Text(NO_MATCH, style=da_styles.EMPTY_TEXT),
            dmc.Button("Clear filters", id=queue_button_id(Q_CLEAR_FILTERS, "empty"), size="xs",
                       variant="default"),
        ]
    )


def bulk_bar(selected: list[str], cards, capability_names: list[str], disabled: bool = False):
    """"N selected" with Assign to, Approve proposals and Reject. Empty when none is selected."""
    if not selected:
        return []
    plan = bulk_plan(selected, cards)
    skip = f" (skips {plan.skipped})" if plan.skipped else ""
    return dmc.Paper(
        dmc.Group(
            [
                dmc.Text(f"{len(selected)} selected", size="sm", fw=600),
                dmc.Select(
                    data=capability_names, id={"type": QUEUE_PICK_TYPE, "uid": BULK_PICK_UID},
                    size="xs", w=170, placeholder="Capability", disabled=disabled,
                ),
                _bulk_button("Assign to", BULK_ASSIGN, disabled),
                _bulk_button(f"Approve proposals{skip}", BULK_APPROVE, disabled or not plan.pairs),
                _bulk_button("Reject", BULK_REJECT, disabled, red=True),
            ],
            gap="xs",
        ),
        withBorder=True, p="xs", mb="xs",
    )


def _bulk_button(label: str, kind: str, disabled: bool, red: bool = False):
    return dmc.Button(
        label, id=queue_button_id(Q_BULK_ASK, state=kind), size="xs", variant="default",
        disabled=disabled, **({"color": "red"} if red else {}),
    )


def bulk_confirm(kind: str, plan: BulkPlan, selected: int, target: str):
    """The confirm box: the count per capability and how many are skipped."""
    if kind == BULK_APPROVE:
        lines = ", ".join(f"{name}: {n}" for name, n in plan.counts.items())
        text = f"Approve {len(plan.pairs)} programs? {lines}."
        if plan.skipped:
            text += f" {plan.skipped} selected programs have no proposal and are skipped."
    elif kind == BULK_ASSIGN:
        text = f"Assign {selected} programs to {target}?"
    else:
        text = f"Reject {selected} programs? They stay out of every capability."
    return dmc.Paper(
        [
            dmc.Text(text, size="sm"),
            dmc.Group(
                [
                    dmc.Button(
                        "Confirm", id=queue_button_id(Q_BULK_DO, cap=target, state=kind), size="xs"
                    ),
                    dmc.Button(
                        "Cancel", id=queue_button_id(Q_CANCEL), size="xs", variant="default"
                    ),
                ],
                mt="xs",
            ),
        ],
        withBorder=True, p="sm", mb="xs",
    )


def review_pane(
    rf: ReviewFilter, folders: list[str], shown: int, total: int, items: list, above: list,
    bar, disabled: bool = False,
):
    """The Review queue view. `above` holds notices and the confirm boxes."""
    return html.Div(
        [
            *above,
            # Sticky: when the page scrolls to show more cards, search and bulk bar stay in view.
            html.Div(
                [
                    control_bar(rf, folders),
                    count_row(shown, total, disabled),
                    html.Div(bar, id=RQ_BAR_ID),
                ],
                style=admin_styles.REVIEW_BAR,
            ),
            html.Div(items or empty_list(), id=RQ_LIST_ID, style=admin_styles.REVIEW_BOX),
        ]
    )
