"""AF-20: save a screenshot of every Admin tab (read view and edit view) at 1366 by 768.

The code reviewer opens these next to docs/admin-reference/. Skipped, not failed, when Playwright
or its browser is missing. The PNGs go to logs/admin-screens/ (Git ignores logs)."""

import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from callbacks.screen_callbacks import da_admin_page_callbacks as admin_cb
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_enhance import add_unassigned
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_rulebook import save_new_version
from layouts.da_admin_page import ADMIN_PATH, ADMIN_TABS, EDITABLE_TABS
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

ADMIN = "admin-0001"
OUT = Path(__file__).resolve().parents[1] / "logs" / "admin-screens"
VIEWPORT = {"width": 1366, "height": 768}


def seed_for_pictures(settings, rulebook):
    """v2 and v3 with change notes (History diff, Restore) and one waiting Unassigned file."""
    # History opens on the version before the active one, so it needs a v3 to show a diff.
    notes = ((1, 4, "Allow four build rounds"), (2, 5, "Allow five build rounds"))
    for base, rounds, note in notes:
        policy = rulebook.policy.model_copy(update={"build_max_rounds": rounds})
        updated = rulebook.model_copy(update={"policy": policy})
        save_new_version(settings.db_path, updated, base, ADMIN, note)
    request = create_request(settings.db_path, "Change the upload limit", "dev-0001")
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        now = datetime.now(UTC)
        add_unassigned(conn, "src/uploads/da_scan.py", "Limits", request.request_id, now)


@pytest.fixture
def live(make_settings, monkeypatch, seed_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    seed_for_pictures(settings, seed_rulebook)
    monkeypatch.setattr(admin_cb, "get_admin_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    server = make_server("127.0.0.1", 0, server_module.create_app().server, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}{ADMIN_PATH}"
    server.shutdown()


def test_af20_sixteen_screenshots_are_saved(make_live_page, live):
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    page = make_live_page(live)
    page.set_viewport_size(VIEWPORT)
    for number, (tab, label, _) in enumerate(ADMIN_TABS, start=1):
        page.get_by_role("tab", name=label, exact=True).click()
        body = page.locator(f"#adm-body-{tab}")
        body.wait_for(timeout=15000)
        page.wait_for_timeout(500)
        stem = f"{number:02d}-{tab}"
        page.screenshot(path=str(OUT / f"{stem}-read.png"))
        if tab in EDITABLE_TABS:
            body.get_by_role("button", name="Edit", exact=True).click()
            bar = page.get_by_text("Nothing changes for developers until you save.")
            bar.wait_for(timeout=10000)
            page.screenshot(path=str(OUT / f"{stem}-edit.png"))
            body.get_by_role("button", name="Cancel", exact=True).click()
        else:
            # Overview and History have no edit view: the second picture is the whole page.
            page.screenshot(path=str(OUT / f"{stem}-full.png"), full_page=True)
    assert len(list(OUT.glob("*.png"))) == 16
