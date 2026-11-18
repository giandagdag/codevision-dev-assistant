"""Phase 11 fix 3, step 9: one search box (AH-12), the tagged header, AI proposals shown (AH-13).
Made-up names only; no AI."""

from agents.da_admin_overview import build_overview
from agents.da_admin_tag_store import save_store
from callbacks.screen_callbacks import da_admin_page_callbacks as page
from layouts.da_admin_catalog_tab import catalog_view

PROPOSED = {
    "state": "proposed", "proposed_capability": "Documents", "confidence": "high",
    "summary": "Writes markdown.", "reason": "fits", "file_hash": "h",
}  # fmt: skip


def _admin(make_settings):
    return make_settings(admin_ids=("admin-0001",), developer_id="admin-0001")


def _store(tmp_path, monkeypatch, modules=None, runs=None):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))
    save_store({"modules": modules or {}, "runs": runs or []}, tmp_path)


def test_ah12_the_box_runs_on_enter_not_per_key(published_rulebook, tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    parts = _walk(catalog_view(published_rulebook))
    box = [c for c in parts if getattr(c, "id", "") == "adm-cat-search"]
    assert len(box) == 1 and box[0].debounce is True
    assert "what the code does" in box[0].placeholder


def test_ah12_name_matches_come_first_then_the_labelled_meaning_matches(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    _store(tmp_path, monkeypatch)
    calls = []

    def fake_search(query, settings, capabilities, tags):
        calls.append(query)
        return [], "The CodeVision index needs building"

    monkeypatch.setattr(page, "meaning_search", fake_search)
    settings = _admin(make_settings)
    name = published_rulebook.rulebook.policy.capabilities[0].name

    table, results = page.catalog_search(settings, name, False)

    assert name in str(table)
    assert calls == [name]  # the meaning search ran once, with the same text
    assert "needs building" in str(results)


def test_the_header_names_the_tag_time_and_links_to_the_repository_tab(
    published_rulebook, tmp_path, monkeypatch
):
    _store(tmp_path, monkeypatch, runs=[{"started_at": "2026-11-14T02:00:05"}])
    shown = str(catalog_view(published_rulebook))
    assert "Programs last tagged 2026-11-14 02:00:05, with index build" in shown
    assert "'tab': 'repo'" in shown and "Repository and index" in shown


def test_the_header_says_so_before_the_first_tagging(published_rulebook, tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    assert "have not been tagged yet" in str(catalog_view(published_rulebook))


def test_ah13_ai_proposals_show_as_cards_and_in_the_overview(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    _store(tmp_path, monkeypatch, modules={"src/x/odd_a.py": PROPOSED, "src/x/odd_b.py": PROPOSED})
    settings = _admin(make_settings)

    queue = page.queue_data(settings)
    shown = str(catalog_view(published_rulebook, queue=queue))
    overview = build_overview(settings)

    assert "From the AI scan" in shown and "odd_a.py" in shown and "odd_b.py" in shown
    assert any("2 AI proposals to review" in item.text for item in overview.attention)


def _walk(node):
    yield node
    kids = getattr(node, "children", None)
    for kid in kids if isinstance(kids, list | tuple) else [kids]:
        if kid is not None and not isinstance(kid, str | int | float):
            yield from _walk(kid)
