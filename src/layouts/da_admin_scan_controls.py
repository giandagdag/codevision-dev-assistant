"""The AI scan buttons on the catalog tab header (fix 11-2, AG-8): two buttons, a confirm box, a
status line and a poll that refreshes it while the job runs. Same shape as the index rebuild."""

import dash_mantine_components as dmc
from dash import dcc

SCAN_ALL_BTN = "adm-scan-all-btn"
SCAN_NEW_BTN = "adm-scan-new-btn"
SCAN_CONFIRM = "adm-scan-confirm"
SCAN_LATER = "adm-scan-later"
SCAN_MODAL = "adm-scan-modal"
SCAN_STATUS = "adm-scan-status"
SCAN_POLL = "adm-scan-poll"
SCAN_MODE = "adm-scan-mode"  # remembers which button opened the box: "all" or "new"
SCAN_TEXT_ALL = "adm-scan-text-all"
SCAN_TEXT_NEW = "adm-scan-text-new"
SCAN_NEW_EXPLAIN = (
    "Asks the AI to read only the programs that are new or changed since the last scan, "
    "and propose a capability. Runs in the background; you can leave the page. "
    "Nothing changes until you approve a proposal."
)
SHOWN, HIDDEN = {}, {"display": "none"}


def scan_explain(count: int) -> str:
    return (
        "Asks the AI to read every program once and propose a capability. "
        f"About {count} programs. Runs in the background; you can leave the page. "
        "Nothing changes until you approve a proposal."
    )


NEW_OR_CHANGED_TIP = "The index is newer than the last scan: some programs may be new or changed."


def scan_controls(running: bool, status: str, out_of_date: bool = False, count: int = 0):
    return dmc.Group(
        [
            dmc.Button("Scan all programs", id=SCAN_ALL_BTN, disabled=running, size="xs"),
            dmc.Tooltip(
                dmc.Button(
                    "Tag new or changed",
                    id=SCAN_NEW_BTN,
                    disabled=running,
                    size="xs",
                    variant="filled" if out_of_date else "light",
                ),
                label=NEW_OR_CHANGED_TIP,
                disabled=not out_of_date,
            ),
            dmc.Text(status, id=SCAN_STATUS, size="sm"),
            dcc.Interval(id=SCAN_POLL, interval=3000),
            dcc.Store(id=SCAN_MODE, data="all"),
            dmc.Modal(
                dmc.Stack(
                    [
                        dmc.Text(scan_explain(count), id=SCAN_TEXT_ALL, size="sm"),
                        dmc.Text(SCAN_NEW_EXPLAIN, id=SCAN_TEXT_NEW, size="sm", style=HIDDEN),
                        dmc.Group(
                            [
                                dmc.Button("Later", id=SCAN_LATER, variant="default"),
                                dmc.Button("Scan", id=SCAN_CONFIRM),
                            ]
                        ),
                    ]
                ),
                id=SCAN_MODAL,
                title="Scan the programs with AI?",
                opened=False,
            ),
        ],
        mb="xs",
    )
