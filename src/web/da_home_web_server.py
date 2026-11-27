"""A stand-in CodeVision shell, for running the Developer Assistant screen at home.

Home only, never copied to work: at work CodeVision's own header, side menu and page routing are
used. This file gives the page what CodeVision gives it (a header, a left menu, and a
dcc.Location), so the page plugs in the same way.

Run: .venv\\Scripts\\python src\\web\\da_home_web_server.py   then open http://127.0.0.1:8050
"""

import sys
from pathlib import Path
from urllib.parse import parse_qs

# Started as a script from src/web, Python only sees this folder. Add src so the imports work.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dash_mantine_components as dmc  # noqa: E402
from dash import Dash, Input, Output, dcc, html  # noqa: E402
from dash_iconify import DashIconify  # noqa: E402

from agents.da_admin_scheduler import start_scheduler  # noqa: E402
from agents.da_build_runner import recover_interrupted_builds  # noqa: E402
from agents.da_safety_net_flow import recover_interrupted_safety_nets  # noqa: E402
from callbacks.screen_callbacks.da_admin_page_callbacks import (  # noqa: E402
    DEV_WRAP_ID,
    register_da_admin_page_callbacks,
)
from callbacks.screen_callbacks.da_capability_map_callbacks import (  # noqa: E402
    register_da_capability_map_callbacks,
)
from callbacks.screen_callbacks.da_developer_assistant_page_callbacks import (  # noqa: E402
    get_settings,
    register_da_developer_assistant_page_callbacks,
)
from callbacks.screen_callbacks.da_inbox_page_callbacks import (  # noqa: E402
    register_da_inbox_page_callbacks,
)
from callbacks.screen_callbacks.da_test_report_page_callbacks import (  # noqa: E402
    register_da_test_report_page_callbacks,
)
from configs.da_config import ConfigError  # noqa: E402
from db_table_functions.da_db import DatabaseBusyError  # noqa: E402
from db_table_functions.db_tbl_da_rulebook import RulebookError, get_active_version  # noqa: E402
from layouts.da_admin_page import ADMIN_CONTENT_ID, ADMIN_PATH  # noqa: E402
from layouts.da_capability_map_view import map_shell  # noqa: E402
from layouts.da_developer_assistant_page import (  # noqa: E402
    DEMO_PAGE_BANNER,
    LOCATION_ID,
    layout,
)
from layouts.da_inbox_page import (  # noqa: E402
    BANNER_ID,
    INBOX_PATH,
    MENU_LINK_ID,
    inbox_shell,
)
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
INBOX_MENU_NAME = "Inbox"
INBOX_MENU_ICON = "tabler:inbox"
DEMO_PAGE_BANNER_ID = "da-demo-page-banner"
DEV_MENU_ID = "da-dev-menu"
ADMIN_MENU_ID = "da-admin-menu"


def active_entries(pathname: str | None) -> tuple[bool, bool, bool]:
    """Which side-menu entry is lit: (Developer Assistant, Admin, Inbox), by the URL."""
    return (
        pathname not in (ADMIN_PATH, INBOX_PATH),
        pathname == ADMIN_PATH,
        pathname == INBOX_PATH,
    )


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
                # "callback-nav": a callback writing the address (admin tab clicks) must not reload the page.
                dcc.Location(id=LOCATION_ID, refresh="callback-nav"),
                dmc.AppShellHeader(_header(), px="md"),
                dmc.AppShellNavbar(_menu(), p="xs"),
                dmc.AppShellMain(
                    [
                        *_demo_banner(),
                        # Seniors only: filled by a callback, hidden at 0 (Phase 10 step 10b).
                        dmc.Alert(
                            id=BANNER_ID, color="orange", variant="light", m="md",
                            style={"display": "none"},
                        ),  # fmt: skip
                        html.Div(layout(), id=DEV_WRAP_ID),
                        html.Div(id=ADMIN_CONTENT_ID),
                        inbox_shell(),
                        map_shell(),
                    ],
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
    register_da_test_report_page_callbacks(app)
    register_da_capability_map_callbacks(app)
    # `?as=<id>` (pretend to be another senior) lives in this home shell only: the inbox code
    # that goes to work never reads it (spec D-G).
    register_da_inbox_page_callbacks(app, identify=as_user, keep_query=keep_as)

    @app.callback(
        Output(DEV_MENU_ID, "active"),
        Output(ADMIN_MENU_ID, "active"),
        Output(MENU_LINK_ID, "active"),
        Input(LOCATION_ID, "pathname"),
    )
    def light_the_current_menu_entry(pathname):
        return active_entries(pathname)

    return app


def _demo_banner() -> list:
    """The fake AI means made-up data: say so on every page (B1 F7). Home shell only."""
    if get_settings().llm_provider != "fake":
        return []
    banner = dmc.Alert(
        DEMO_PAGE_BANNER, id=DEMO_PAGE_BANNER_ID, color="violet", variant="light", m="md"
    )
    return [banner]


def as_user(search: str | None) -> str:
    """Who the home shell says is looking: `?as=<id>` if given, else the home developer ID."""
    wanted = parse_qs((search or "").lstrip("?")).get("as")
    return wanted[0].strip() if wanted and wanted[0].strip() else get_settings().developer_id


def keep_as(search: str | None) -> str:
    """The `&as=<id>` to keep on the inbox links, or nothing."""
    wanted = parse_qs((search or "").lstrip("?")).get("as")
    return f"&as={wanted[0].strip()}" if wanted and wanted[0].strip() else ""


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
            id=DEV_MENU_ID,
            label=MENU_NAME,
            leftSection=DashIconify(icon=MENU_ICON, width=20),
            active=True,  # a callback moves this to the page you are on (fix 11-1, AF-1)
            href="/",
        ),
        dmc.NavLink(
            id=ADMIN_MENU_ID,
            label=ADMIN_MENU_NAME,
            leftSection=DashIconify(icon=ADMIN_MENU_ICON, width=20),
            href=ADMIN_PATH,
        ),
        dmc.NavLink(  # the label gets "(2)" from a callback when this user is a senior
            id=MENU_LINK_ID,
            label=INBOX_MENU_NAME,
            leftSection=DashIconify(icon=INBOX_MENU_ICON, width=20),
            href=INBOX_PATH,
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
    start_scheduler(settings)  # Nightly refresh, only while this server runs
    create_app().run(host=HOST, port=PORT, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
