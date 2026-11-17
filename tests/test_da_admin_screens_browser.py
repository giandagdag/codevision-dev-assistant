"""AF-20: save a screenshot of every Admin tab (read view and edit view) at 1366 by 768.

The code reviewer opens these next to docs/admin-reference/. Skipped, not failed, when Playwright
or its browser is missing. The PNGs go to logs/admin-screens/ (Git ignores logs)."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from agents.da_admin_index import record_run
from agents.da_admin_tagger import ScriptedTaggerClient, run_tagging
from agents.da_code_index import PIECES_NAME
from callbacks.screen_callbacks import da_admin_page_callbacks as admin_cb
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_enhance import add_unassigned
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_rulebook import save_new_version
from layouts.da_admin_common import TAB_CAPABILITY, TAB_CODING
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
def live(make_settings, monkeypatch, seed_rulebook, tmp_path):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    seed_for_pictures(settings, seed_rulebook)
    # A built index, so Index health shows its tiles and Recent refreshes has a run.
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))
    built = {
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "source": "src/data/da_fake_codevision",
        "pieces": [{"path": "limits_batch.py"}, {"path": "limits_batch.py"}, {"path": "menu.py"}],
    }
    (tmp_path / PIECES_NAME).write_text(json.dumps(built), encoding="utf-8")
    record_run(ADMIN, datetime.now(), True, 3, [], "ok", tmp_path)
    # The AI scan (made-up script), so the queue has AI cards and "creates markdown" finds modules.
    fake_root = Path(__file__).resolve().parents[1] / "src" / "data" / "da_fake_codevision"
    fake_paths = sorted(p.relative_to(fake_root).as_posix() for p in fake_root.rglob("*.py"))
    run_tagging(
        fake_paths, fake_root, seed_rulebook.policy.capabilities, ScriptedTaggerClient(),
        ADMIN, directory=tmp_path,
    )
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
        # The whole read page too, in its own folder (17 Nov: Gian reviews on his phone, and the
        # 768-high picture hid the lower windows). The sixteen above stay sixteen.
        (OUT / "full").mkdir(exist_ok=True)
        page.screenshot(path=str(OUT / "full" / f"{stem}.png"), full_page=True)
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


def test_ag16_fix2_screenshots_are_saved(make_live_page, live):
    """AG-16: the catalog in both search modes, the queue, and Coding standards with SonarQube.
    They go in a sub folder so the sixteen above stay sixteen."""
    folder = OUT / "fix2"
    folder.mkdir(parents=True, exist_ok=True)
    labels = {tab: label for tab, label, _ in ADMIN_TABS}
    page = make_live_page(live)
    page.set_viewport_size(VIEWPORT)
    page.get_by_role("tab", name=labels[TAB_CAPABILITY], exact=True).click()
    page.locator(f"#adm-body-{TAB_CAPABILITY}").wait_for(timeout=15000)
    page.wait_for_timeout(500)
    page.screenshot(path=str(folder / "catalog-names.png"))
    page.get_by_text("What the code does", exact=True).click()
    page.get_by_placeholder("Describe what the code does", exact=False).fill("creates markdown")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(folder / "catalog-meaning.png"))
    page.locator("#adm-queue").screenshot(path=str(folder / "queue.png"))
    page.get_by_role("tab", name=labels[TAB_CODING], exact=True).click()
    page.locator(f"#adm-body-{TAB_CODING}").wait_for(timeout=15000)
    page.wait_for_timeout(500)
    page.screenshot(path=str(folder / "coding-sonar.png"), full_page=True)
    assert len(list(folder.glob("*.png"))) == 4
