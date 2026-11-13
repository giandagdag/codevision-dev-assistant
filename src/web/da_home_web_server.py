"""A stand-in CodeVision shell, for running the Developer Assistant screen at home.

Home only, never copied to work: at work CodeVision's own header, side menu and page routing are
used. This file gives the page what CodeVision gives it (a header, a left menu, and a
dcc.Location), so the page plugs in the same way.

Run: .venv\\Scripts\\python src\\web\\da_home_web_server.py   then open http://127.0.0.1:8050
"""

import sys
from pathlib import Path

# Started as a script from src/web, Python only sees this folder. Add src so the imports work.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dash_mantine_components as dmc  # noqa: E402
from dash import Dash, dcc, html  # noqa: E402
from dash_iconify import DashIconify  # noqa: E402

from agents.da_build_runner import recover_interrupted_builds  # noqa: E402
from agents.da_safety_net_flow import recover_interrupted_safety_nets  # noqa: E402
from callbacks.screen_callbacks.da_admin_page_callbacks import (  # noqa: E402
    DEV_WRAP_ID,
    register_da_admin_page_callbacks,
)
from callbacks.screen_callbacks.da_developer_assistant_page_callbacks import (  # noqa: E402
    get_settings,
    register_da_developer_assistant_page_callbacks,
)
from configs.da_config import ConfigError  # noqa: E402
from db_table_functions.da_db import DatabaseBusyError  # noqa: E402
from db_table_functions.db_tbl_da_rulebook import RulebookError, get_active_version  # noqa: E402
from layouts.da_admin_page import ADMIN_CONTENT_ID, ADMIN_PATH  # noqa: E402
from layouts.da_developer_assistant_page import LOCATION_ID, layout  # noqa: E402
from styles import da_styles  # noqa: E402

# Local only (rule R13): nobody else on the network can reach this server.
HOST = "127.0.0.1"
PORT = 8050

# The side menu: only the Developer Assistant (Gian, 29 Oct 2026). At work CodeVision's own
# menu is used.
MENU_NAME = "Developer Assistant"
MENU_ICON = "tabler:code"
ADMIN_MENU_NAME = "Admin"
ADMIN_MENU_ICON = "tabler:settings"


def create_app() -> Dash:
    app = Dash(
        __name__,
        title="CodeVision Developer Assistant",
        # The workspace is drawn by callbacks, so its buttons do not exist at start-up.
        suppress_callback_exceptions=True,
    )
    app.layout = dmc.MantineProvider(
        dmc.AppShell(
            [
                dcc.Location(id=LOCATION_ID),
                dmc.AppShellHeader(_header(), px="md"),
                dmc.AppShellNavbar(_menu(), p="xs"),
                dmc.AppShellMain(
                    [html.Div(layout(), id=DEV_WRAP_ID), html.Div(id=ADMIN_CONTENT_ID)],
                    bg=da_styles.CANVAS,
                ),
            ],
            header={"height": 60},
            navbar={"width": 240, "breakpoint": "sm"},
            padding=0,
        )
    )
    register_da_developer_assistant_page_callbacks(app)
    register_da_admin_page_callbacks(app)
    return app


def _header() -> dmc.Group:
    return dmc.Group(
        [
            dmc.Group(
                [
                    dmc.Text("CODEVISION", fw=800, size="lg", c=da_styles.NAVY),
                    dmc.Text("Developer Assistant", c=da_styles.MUTED),
                ]
            ),
            dmc.Text(get_settings().developer_id, size="sm", c=da_styles.MUTED),
        ],
        justify="space-between",
        h="100%",
    )


def _menu() -> list:
    return [
        dmc.NavLink(
            label=MENU_NAME,
            leftSection=DashIconify(icon=MENU_ICON, width=20),
            active=True,
            href="/",
        ),
        dmc.NavLink(
            label=ADMIN_MENU_NAME,
            leftSection=DashIconify(icon=ADMIN_MENU_ICON, width=20),
            href=ADMIN_PATH,
        ),
    ]


def main() -> int:
    try:
        settings = get_settings()
        if get_active_version(settings.db_path) is None:
            print(
                "No rulebook has been published yet. Run this once first:\n"
                "  .venv\\Scripts\\python src\\da_load_starter_rulebook.py"
            )
            return 1
    except (ConfigError, RulebookError, DatabaseBusyError) as error:
        print(error)
        return 1
    # At start-up no build can really still be running, so one marked running was cut off by a
    # restart. Mark it paused; Try again resumes it from the last saved step (spec section 10).
    for request_id in recover_interrupted_builds(settings):
        print(f"Build of {request_id} was paused by the restart. Open it and press Try again.")
    # Same for a safety net that was being written (Phase 9, F3): Try again runs it again.
    for request_id in recover_interrupted_safety_nets(settings):
        print(f"The safety net of {request_id} was cut off by the restart. Press Try again.")
    create_app().run(host=HOST, port=PORT, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
