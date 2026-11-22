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
from agents.da_admin_tag_store import save_store
from agents.da_admin_tagger import ScriptedTaggerClient, run_tagging
from agents.da_code_graph import build_graph, save_graph
from agents.da_code_index import PIECES_NAME
from callbacks.screen_callbacks import da_admin_page_callbacks as admin_cb
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_enhance import add_unassigned
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_rulebook import save_new_version
from layouts.da_admin_common import TAB_CAPABILITY, TAB_CODING
from layouts.da_admin_page import ADMIN_PATH, ADMIN_TABS, EDITABLE_TABS
from layouts.da_capability_map_view import MAP_PATH
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
    box = page.get_by_placeholder("Search capability, program, person", exact=False)
    box.fill("creates markdown")
    box.press("Enter")  # one box, runs on Enter (fix 3, D-E)
    page.wait_for_timeout(1500)
    page.screenshot(path=str(folder / "catalog-meaning.png"))
    page.locator("#adm-cat-view").get_by_text("Review queue").click()  # its own view (G4 L7)
    page.locator("#adm-rq-list").wait_for(timeout=15000)
    page.locator("#adm-queue").screenshot(path=str(folder / "queue.png"))
    page.get_by_role("tab", name=labels[TAB_CODING], exact=True).click()
    page.locator(f"#adm-body-{TAB_CODING}").wait_for(timeout=15000)
    page.wait_for_timeout(500)
    page.screenshot(path=str(folder / "coding-sonar.png"), full_page=True)
    assert len(list(folder.glob("*.png"))) == 4


def test_g1_8_capability_map_pictures(make_live_page, live, tmp_path):
    """G1-8: the map opens with bubbles, a tap goes down one level, no console errors.
    The live fixture set DA_CODE_INDEX_DIR to tmp_path, so the graph is saved there."""
    fake_root = Path(__file__).resolve().parents[1] / "src" / "data" / "da_fake_codevision"
    paths = sorted(p.relative_to(fake_root).as_posix() for p in fake_root.rglob("*.py"))
    save_graph(build_graph(fake_root, paths).graph, tmp_path)
    OUT.mkdir(parents=True, exist_ok=True)
    page = make_live_page(live)
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_viewport_size(VIEWPORT)
    page.goto(live.replace(ADMIN_PATH, MAP_PATH))  # listeners are attached before this open
    page.locator("#da-map-graph canvas").first.wait_for(timeout=15000)
    cy = "document.getElementById('da-map-graph')._cyreg.cy"
    page.wait_for_function(f"{cy}.nodes().length > 0", timeout=15000)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(OUT / "map-level1.png"))
    page.evaluate(f"{cy}.nodes()[0].emit('tap')")  # cytoscape's own tap event, as a click gives
    page.wait_for_function(
        "document.getElementById('da-map-crumb').innerText.includes(' > ')", timeout=15000
    )
    page.wait_for_timeout(1000)
    page.screenshot(path=str(OUT / "map-capability.png"))
    assert page.evaluate(f"{cy}.nodes().length") > 0
    assert errors == []


def test_g2_4_dense_capability_picture(make_live_page, live, tmp_path):
    """G2-4: 40 made-up modules with long names in one capability (they have no tag, so they
    all sit in 'Unassigned'), linked in a ring; the picture is saved as map-dense.png."""
    names = [f"da_example_long_module_name_{i:02d}" for i in range(40)]
    files = {}
    for i, name in enumerate(names):
        other = f"src.agents.{names[(i + 1) % 40]}"
        files[f"src/agents/{name}.py"] = {
            "module": f"src.agents.{name}", "defs": {"run": "function"},
            "edges": [["imports", f"src.agents.{name}", other]], "unresolved": 0,
        }
    save_graph({"files": files}, tmp_path)
    OUT.mkdir(parents=True, exist_ok=True)
    page = make_live_page(live)
    page.set_viewport_size(VIEWPORT)
    page.goto(live.replace(ADMIN_PATH, MAP_PATH))
    cy = "document.getElementById('da-map-graph')._cyreg.cy"
    page.wait_for_function(f"{cy}.nodes().length > 0", timeout=15000)
    page.evaluate(f"{cy}.getElementById('Unassigned').emit('tap')")
    page.wait_for_function(f"{cy}.nodes().length >= 40", timeout=15000)
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "map-dense.png"))
    assert page.evaluate(f"{cy}.nodes().length") == 40


def test_g2_1_no_console_errors_on_map_admin_and_developer_pages(make_live_page, live):
    """G2-1 (P38): the workspace callbacks no longer read da-ws-ctx on pages without it."""
    page = make_live_page(live)
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    for path in (MAP_PATH, ADMIN_PATH, "/"):
        page.goto(live.replace(ADMIN_PATH, path))
        page.wait_for_timeout(1500)
    assert errors == []


WIDTHS = ({"width": 1366, "height": 768}, {"width": 1920, "height": 1080})
PAIR_JS = """() => [...document.querySelectorAll('#adm-body-charter div')]
  .filter(d => getComputedStyle(d).display === 'grid' && d.children.length === 2)
  .map(d => [...d.children].map(c => c.getBoundingClientRect().height))"""


def test_g4_20_26_charter_review_queue_and_bulk_bar_pictures(make_live_page, live):
    """G4-20 and G4-26: the charter pairs end within 120 px of each other; the Review queue (a
    filter on) and the bulk bar are saved at 1366 and 1920 px, in logs/admin-screens/g4."""
    folder = OUT / "g4"
    folder.mkdir(parents=True, exist_ok=True)
    labels = {tab: label for tab, label, _ in ADMIN_TABS}
    for size in WIDTHS:
        page = make_live_page(live)  # a fresh page: the filter is kept, so it must start off
        page.set_viewport_size(size)
        page.get_by_role("tab", name=labels["charter"], exact=True).click()
        page.locator("#adm-body-charter").wait_for(timeout=15000)
        page.wait_for_timeout(500)
        pairs = page.evaluate(PAIR_JS)
        assert len(pairs) >= 2
        for left, right in pairs:
            assert abs(left - right) <= 120
        page.screenshot(path=str(folder / f"charter-{size['width']}.png"), full_page=True)
        page.get_by_role("tab", name=labels[TAB_CAPABILITY], exact=True).click()
        page.locator(f"#adm-body-{TAB_CAPABILITY}").wait_for(timeout=15000)
        page.locator("#adm-cat-view").get_by_text("Review queue").click()
        page.locator("#adm-rq-list").wait_for(timeout=15000)
        page.get_by_text("AI scan", exact=True).click()  # a filter on
        page.get_by_text("Showing 2 of 3").wait_for(timeout=10000)  # the filter really applied
        page.screenshot(path=str(folder / f"review-{size['width']}.png"))
        page.locator("#adm-rq-list input[type=checkbox]").first.check()
        page.get_by_text("1 selected").wait_for(timeout=10000)
        page.screenshot(path=str(folder / f"bulk-{size['width']}.png"))
    names = [f"{stem}-{w['width']}.png" for stem in ("charter", "review", "bulk") for w in WIDTHS]
    assert all((folder / name).exists() for name in names)


ROW_HEIGHTS_JS = """() => [...document.querySelectorAll('#adm-body-capability tbody tr')].map(tr =>
  [...tr.querySelectorAll('input:not([type=hidden]), textarea')]
    .filter(e => e.offsetHeight > 0).map(e => e.getBoundingClientRect().height))"""
CUT_PATHS_JS = """() => [...document.querySelectorAll('.mantine-Modal-body td code')]
  .filter(c => c.scrollWidth > c.clientWidth + 1).map(c => c.innerText)"""


def test_g4_15_catalog_edit_rows_have_even_inputs_and_modal_paths_are_not_cut(
    make_live_page, live
):
    """G4-15 at 1366 and 1920 px: inputs of one row are equally high (2 px); no path is cut."""
    for size in WIDTHS:
        page = make_live_page(live)
        page.set_viewport_size(size)
        page.get_by_role("tab", name="Capability catalog", exact=True).click()
        body = page.locator(f"#adm-body-{TAB_CAPABILITY}")
        body.get_by_role("button", name="Edit", exact=True).click()
        page.get_by_text("Nothing changes for developers until you save.").wait_for(timeout=10000)
        rows = [heights for heights in page.evaluate(ROW_HEIGHTS_JS) if len(heights) > 1]
        assert rows
        for heights in rows:
            assert max(heights) - min(heights) <= 2
        body.get_by_role("button", name="Browse modules...").first.click()
        page.locator(".mantine-Modal-body td code").first.wait_for(timeout=10000)
        assert page.evaluate(CUT_PATHS_JS) == []


VISIBLE_JS = """() => {
  const bar = document.querySelector('#adm-rq-search').closest('div[style*="sticky"]');
  const box = document.querySelector('#adm-rq-list');
  const top = bar.getBoundingClientRect().bottom;
  const bottom = Math.min(box.getBoundingClientRect().bottom, window.innerHeight);
  const rows = [...box.children].filter(c => c.querySelector('input[type=checkbox]'));
  const seen = rows.filter(r => {
    const b = r.getBoundingClientRect();
    return b.top >= top - 1 && b.bottom <= bottom + 1;
  });
  return {seen: seen.length, page: document.documentElement.scrollHeight,
          barTop: bar.getBoundingClientRect().top};
}"""


def test_g4_22_91_cards_the_page_does_not_grow_and_eight_cards_show(
    make_live_page, live, tmp_path
):
    """G4-22: the list scrolls in its own box, the bar stays in view, 8 cards at 1920 x 1080."""
    modules = {
        f"agent_flows/p{n:02d}.py": {
            "summary": "Does a thing.", "proposed_capability": "Limits", "confidence": "high",
            "reason": "because", "state": "proposed",
        }
        for n in range(91)
    }
    save_store({"modules": modules, "runs": []}, tmp_path)
    page = make_live_page(live)
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.get_by_role("tab", name="Capability catalog", exact=True).click()
    page.locator("#adm-cat-view").get_by_text("Review queue").click()
    page.locator("#adm-rq-count").wait_for(timeout=15000)
    page.wait_for_timeout(500)
    page.locator("#adm-rq-list").evaluate("e => e.scrollTop = 1500")  # scroll the list itself
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")  # well past the bar
    page.wait_for_timeout(500)
    got = page.evaluate(VISIBLE_JS)
    assert got["page"] < 2200  # 91 cards do not make the page taller than one box
    assert -1 <= got["barTop"] < 100  # sticky: the bar rode up to the top, it did not scroll off
    assert got["seen"] >= 8
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / "review-91.png"))  # not in g4/: that folder is counted
