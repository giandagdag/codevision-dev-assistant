"""G6-14: the capability map drawn at 1366 and 1920 px with a 13-capability catalog (made up).

No label may overlap a bubble or another label (boxes read from cytoscape), at most 3 links are
drawn per capability, and Unassigned is not drawn. Pictures go to logs/admin-screens/g6. Skipped,
not failed, when Playwright or its browser is missing."""

import json
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from agents.da_code_graph import save_graph
from callbacks.screen_callbacks import da_capability_map_callbacks as map_cb
from layouts.da_capability_map_view import MAP_PATH
from pydantic_classes.da_rulebook_models import Capability
from web import da_home_web_server as server_module

OUT = Path(__file__).resolve().parents[1] / "logs" / "admin-screens" / "g6"
SIZES = (
    {"width": 1366, "height": 768},
    {"width": 1920, "height": 1080},
)
BUSINESS = ["ingestion", "markdown", "embedding", "reports", "limits", "expiry", "search",
            "tagging", "review", "workspace"]  # fmt: skip
FOUNDATIONS = ["config", "classes", "database"]
# Per capability: the box of every bubble, and of every label (the strip under its bubble).
BOXES_JS = """() => {
  const cy = document.getElementById('da-map-graph')._cyreg.cy;
  const nodes = cy.nodes().map(n => {
    const bubble = n.renderedBoundingBox({includeLabels: false, includeOverlays: false});
    const full = n.renderedBoundingBox({includeLabels: true, includeOverlays: false});
    return {id: n.id(), bubble,
            label: {x1: full.x1, x2: full.x2, y1: bubble.y2, y2: full.y2}};
  });
  const degree = {};
  cy.edges().forEach(e => {
    for (const end of [e.source().id(), e.target().id()]) degree[end] = (degree[end] || 0) + 1;
  });
  return {nodes, degree, edges: cy.edges().length, width: cy.width(), height: cy.height()};
}"""


def make_catalog() -> list[Capability]:
    """The shared 13-capability fake catalog (S7); the folder of each is its slug, same order."""
    from agents.da_search_index import DATA_FOLDER

    rows = json.loads((DATA_FOLDER / "da_fake_catalog_13.json").read_text(encoding="utf-8"))
    return [
        Capability(**row, named_senior="Lead", path_patterns=[f"{slug}/*"])
        for row, slug in zip(rows["capabilities"], [*BUSINESS, *FOUNDATIONS], strict=True)
    ]


def make_graph() -> dict:
    """One module per capability; each business module calls four others (3 to 6 times) and every
    foundation; three modules sit in no capability."""
    files = {}
    for i, slug in enumerate(BUSINESS):
        edges = []
        for step, calls in ((1, 6), (2, 4), (3, 3), (5, 5)):
            other = BUSINESS[(i + step) % len(BUSINESS)]
            edges += [["imports", f"{slug}.mod", f"{other}.mod"]] * calls
        edges += [["imports", f"{slug}.mod", f"{f}.mod"] for f in FOUNDATIONS]
        files[f"{slug}/mod.py"] = {"module": f"{slug}.mod", "defs": {"run": "function"},
                                   "edges": edges, "unresolved": 0}  # fmt: skip
    for slug in FOUNDATIONS:
        files[f"{slug}/mod.py"] = {"module": f"{slug}.mod", "defs": {"run": "function"},
                                   "edges": [], "unresolved": 0}  # fmt: skip
    for n in range(3):
        files[f"misc/odd{n}.py"] = {"module": f"misc.odd{n}", "defs": {"run": "function"},
                                    "edges": [["imports", f"misc.odd{n}", "ingestion.mod"]],
                                    "unresolved": 0}  # fmt: skip
    return {"files": files}


def overlap(a: dict, b: dict) -> bool:
    return a["x1"] < b["x2"] and b["x1"] < a["x2"] and a["y1"] < b["y2"] and b["y1"] < a["y2"]


@pytest.fixture
def live(make_settings, monkeypatch, tmp_path):
    settings = make_settings()
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))
    save_graph(make_graph(), tmp_path)
    monkeypatch.setattr(map_cb, "catalog_capabilities", make_catalog)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    server = make_server("127.0.0.1", 0, server_module.create_app().server, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}{MAP_PATH}"
    server.shutdown()


def test_g6_14_no_label_overlaps_at_1366_and_1920(make_live_page, live):
    OUT.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        page = make_live_page(live)
        page.set_viewport_size(size)
        page.reload()  # lay the map out at this width
        page.wait_for_function(
            "() => { const el = document.getElementById('da-map-graph');"
            " return el && el._cyreg && el._cyreg.cy.nodes().length >= 10; }", timeout=20000)
        page.wait_for_timeout(800)
        found = page.evaluate(BOXES_JS)
        nodes = found["nodes"]
        for n in nodes:  # the whole picture is inside the frame (a vacuous pass is no pass)
            assert n["bubble"]["x1"] >= 0 and n["label"]["x2"] <= found["width"], (size, n["id"])
            assert n["bubble"]["y1"] >= 0 and n["label"]["y2"] <= found["height"], (size, n["id"])
        ids = [n["id"] for n in nodes]
        assert "Unassigned" not in ids and len(ids) == 10  # foundations are chips, not bubbles
        assert max(found["degree"].values()) <= 3
        for a in nodes:
            for b in nodes:
                if a["id"] == b["id"]:
                    continue
                assert not overlap(a["label"], b["bubble"]), (size, a["id"], b["id"])
                assert not overlap(a["label"], b["label"]), (size, a["id"], b["id"])
        page.screenshot(path=str(OUT / f"map-{size['width']}.png"))


def test_click_on_empty_space_clears_the_focus(make_live_page, live):  # G6 C4, parked item G6-a
    page = make_live_page(live)
    page.wait_for_function(
        "() => { const el = document.getElementById('da-map-graph');"
        " return el && el._cyreg && el._cyreg.cy.nodes().length >= 10; }", timeout=20000)
    cy = "document.getElementById('da-map-graph')._cyreg.cy"
    page.wait_for_timeout(1000)  # let the page finish its first draw before the tap
    page.evaluate(f"() => {cy}.nodes()[0].emit('tap')")
    page.wait_for_function(f"() => {cy}.nodes('.faded').length > 0", timeout=10000)
    page.evaluate(f"() => {cy}.emit('tap')")  # the target is the picture itself: empty space
    page.wait_for_function(f"() => {cy}.nodes('.faded').length === 0", timeout=10000)
