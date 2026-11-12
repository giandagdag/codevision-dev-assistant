"""Callbacks of the Admin console (Phase 11a).

Own file: it imports nothing from the developer page callbacks, so the two screens can be copied
and changed apart (spec 11-44). Step 5 holds only the access check and the page choice.
"""

from functools import lru_cache

from dash import Input, Output

from agents.da_admin_access import is_admin
from configs.da_config import Settings, load_settings
from db_table_functions.db_tbl_da_rulebook import get_active_version
from layouts.da_admin_page import ADMIN_CONTENT_ID, ADMIN_PATH, admin_page, refusal_page

LOCATION_ID = "url"  # the same dcc.Location the home shell draws (spec D-B)
DEV_WRAP_ID = "da-dev-wrap"


@lru_cache(maxsize=1)
def get_admin_settings() -> Settings:
    """Read the settings once. Tests replace this."""
    return load_settings()


def admin_content(settings: Settings, pathname: str | None):
    """What the admin area holds for this path: nothing, the refusal, or the console."""
    if pathname != ADMIN_PATH:
        return None
    if not is_admin(settings, settings.developer_id):
        return refusal_page()
    active = get_active_version(settings.db_path)
    if active is None:
        return refusal_page()
    return admin_page(active)


def developer_page_style(pathname: str | None) -> dict:
    """The developer page stays built but hidden on /admin, so its layout is not touched."""
    return {"display": "none"} if pathname == ADMIN_PATH else {}


def register_da_admin_page_callbacks(app) -> None:
    @app.callback(
        Output(ADMIN_CONTENT_ID, "children"),
        Output(DEV_WRAP_ID, "style"),
        Input(LOCATION_ID, "pathname"),
    )
    def show_page(pathname):
        return admin_content(get_admin_settings(), pathname), developer_page_style(pathname)
