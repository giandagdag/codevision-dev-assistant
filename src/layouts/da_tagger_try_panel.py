"""Try the tagger panel on the Review queue view (Fix G5 R7). Plain components."""

import dash_mantine_components as dmc
from dash import html

from layouts.da_admin_job_bar import locked

TRY_PICK = "adm-trytag-pick"
TRY_BTN = "adm-trytag-btn"
TRY_OUT = "adm-trytag-out"
TRY_RAW = "adm-trytag-raw"
SHOWN_PATHS = 200  # options shown at once; the picker is searchable
NOTE = "Runs one AI call and shows the reply. Nothing is saved."


def tagger_try_panel(paths: list[str]):
    picker = dmc.Select(
        id=TRY_PICK, data=paths, searchable=True, limit=SHOWN_PATHS,
        placeholder="Pick a program", size="xs", w=360,
    )
    body = dmc.Stack(
        [
            dmc.Text(NOTE, size="xs", c="dimmed"),
            dmc.Group(
                [
                    picker,
                    locked("try", dmc.Button("Try", id=TRY_BTN, size="xs", variant="default")),
                ],
                gap="xs",
            ),
            dmc.Text("", id=TRY_OUT, size="sm"),
            dmc.Code("", id=TRY_RAW, block=True, style={"display": "none"}),
        ],
        gap="xs",
    )
    # Closed at first: an Admin tool, so it must not push the review list down the page.
    return html.Details(
        [
            html.Summary(
                "Try the tagger on one program",
                style={"fontWeight": 600, "fontSize": 14, "cursor": "pointer"},
            ),
            body,
        ],
        style={"marginTop": 12},
    )
