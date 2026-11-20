"""Fix G4 L7 to L10: the Review queue view, scrolling box, filters kept, bulk bar (made-up data)."""

from agents.da_admin_overview import build_overview
from agents.da_admin_review import ReviewFilter
from agents.da_admin_tag_store import read_tags, save_store
from agents.da_tag_versions import list_versions as list_tag_versions
from callbacks.screen_callbacks import da_admin_page_callbacks as page
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions
from layouts.da_admin_catalog_tab import catalog_view, queue_button_id

ADMIN = "admin-0001"


def entry(capability, confidence="high", summary="Does a thing."):
    return {
        "summary": summary, "proposed_capability": capability, "confidence": confidence,
        "reason": "because", "state": "proposed",
    }  # fmt: skip


def setup(tmp_path, monkeypatch, modules):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))
    save_store({"modules": modules, "runs": []}, tmp_path)


def walk(node):
    yield node
    kids = getattr(node, "children", None)
    for kid in kids if isinstance(kids, list | tuple) else [kids]:
        if kid is not None and not isinstance(kid, str | int | float):
            yield from walk(kid)


def text_of(node) -> str:
    return " ".join(str(getattr(n, "children", "")) for n in walk(node))


def admin(make_settings):
    return make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)


def by_id(node, wanted):
    return next(n for n in walk(node) if getattr(n, "id", None) == wanted)


def test_g4_22_the_list_scrolls_in_its_own_box_and_the_bar_is_outside_it(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    modules = {f"agent_flows/p{n:02d}.py": entry("Uploads") for n in range(91)}
    setup(tmp_path, monkeypatch, modules)

    view = catalog_view(published_rulebook, queue=page.queue_data(admin(make_settings)))

    box = by_id(view, "adm-rq-list")
    assert box.style["height"] == "calc(100vh - 260px)" and box.style["minHeight"] == "420px"
    assert box.style["overflowY"] == "auto"
    assert len(box.children) > 91  # 91 compact rows plus the section line
    assert not any(getattr(n, "id", None) == "adm-rq-search" for n in walk(box))  # bar not inside
    switch = by_id(view, "adm-cat-view")
    assert switch.data[1]["label"] == "Review queue (91)"
    assert "Showing 91 of 91" in text_of(view)


def test_the_overview_line_opens_the_review_queue(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    setup(tmp_path, monkeypatch, {"a/x.py": entry("Uploads")})
    items = build_overview(admin(make_settings)).attention

    item = next(i for i in items if "AI proposal" in i.text)

    assert item.filter == "review_queue"


def test_g4_24_filter_search_and_selection_stay_after_an_approval(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    modules = {
        "web/a.py": entry("Uploads", summary="COBOL bridge"),
        "web/b.py": entry("Uploads", summary="COBOL copy"),
        "agent_flows/c.py": entry("Uploads", summary="plain"),
    }
    setup(tmp_path, monkeypatch, modules)
    settings = admin(make_settings)
    review = {"view": "queue", "filter": ReviewFilter(search="cobol"), "selected": []}

    action = queue_button_id("ai_approve", "web/a.py", "Uploads")
    content = page.run_queue_action(settings, action, {}, {}, 1, review)

    assert by_id(content, "adm-rq-search").value == "cobol"
    assert by_id(content, "adm-cat-view").value == "queue"
    assert "Showing 1 of 2" in text_of(content)  # b.py shown; c.py hidden by the search


def test_g4_25_approve_proposals_saves_one_version_and_the_box_says_what_it_skips(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    modules = {
        "zz/a.py": entry("Uploads"), "zz/b.py": entry("Uploads"), "zz/c.py": entry("Uploads"),
        "zz/d.py": entry(""), "zz/e.py": entry(""),
    }  # fmt: skip
    setup(tmp_path, monkeypatch, modules)
    settings = admin(make_settings)
    review = {"view": "queue", "filter": ReviewFilter(), "selected": sorted(modules)}

    asked = page.run_queue_action(
        settings, queue_button_id("bulk_ask", 0, "", "approve"), {}, {}, 1, review
    )
    assert "Approve 3 programs?" in text_of(asked)
    assert "2 selected programs have no proposal and are skipped" in text_of(asked)

    done = page.run_queue_action(
        settings, queue_button_id("bulk_do", 0, "", "approve"), {}, {}, 1, review
    )
    active = get_active_version(settings.db_path)
    assert len(list_versions(settings.db_path)) == 2
    assert active.change_note == "AI scan: 3 programs approved"
    assert "The catalog is now v2" in text_of(done)
    assert read_tags(tmp_path)["zz/a.py"]["state"] == "approved"
    assert read_tags(tmp_path)["zz/d.py"]["state"] == "proposed"


def test_bulk_assign_needs_a_capability_and_bulk_reject_is_one_tag_version(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    setup(tmp_path, monkeypatch, {"zz/a.py": entry(""), "zz/b.py": entry("")})
    settings = admin(make_settings)
    review = {"view": "queue", "filter": ReviewFilter(), "selected": ["zz/a.py", "zz/b.py"]}

    refused = page.run_queue_action(
        settings, queue_button_id("bulk_ask", 0, "", "assign"), {}, {}, 1, review
    )
    assert "Choose a capability first." in text_of(refused)

    before = len(list_tag_versions(tmp_path))
    page.run_queue_action(
        settings, queue_button_id("bulk_do", 0, "", "reject"), {}, {}, 1, review
    )
    assert read_tags(tmp_path)["zz/a.py"]["state"] == "rejected"
    assert len(list_tag_versions(tmp_path)) - before <= 2  # starting snapshot plus one decision


def test_select_all_shown_ticks_only_what_the_filter_shows(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    modules = {"web/a.py": entry("Uploads"), "agent_flows/b.py": entry("Uploads")}
    setup(tmp_path, monkeypatch, modules)
    review = {"view": "queue", "filter": ReviewFilter(folder=("web",)), "selected": []}

    content = page.run_queue_action(
        admin(make_settings), queue_button_id("select_all"), {}, {}, 1, review
    )

    assert "1 selected" in text_of(content)


def test_clear_filters_resets_the_search(make_settings, published_rulebook, tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, {"web/a.py": entry("Uploads")})
    review = {"view": "queue", "filter": ReviewFilter(search="zzz"), "selected": []}

    content = page.run_queue_action(
        admin(make_settings), queue_button_id("clear_filters"), {}, {}, 1, review
    )

    assert by_id(content, "adm-rq-search").value == ""


def test_the_review_states_come_back_as_a_filter_and_ticks():
    states = [
        [], [], [{"value": 1}], {"value": "cobol"}, {"value": ["ai"]}, {"value": None},
        {"value": ["high"]}, {"value": ["web"]}, {"value": "path"}, {"value": "queue"},
        [{"id": {"type": "adm-rq-sel", "path": "web/a.py"}, "value": True},
         {"id": {"type": "adm-rq-sel", "path": "web/b.py"}, "value": False}],
    ]  # fmt: skip

    review = page.review_from_states(states)

    assert review["view"] == "queue" and review["selected"] == ["web/a.py"]
    assert review["filter"].search == "cobol" and review["filter"].sort == "path"
    assert review["filter"].confidence == ("high",) and review["filter"].folder == ("web",)
    assert page.review_from_states([[], [], []]) == {}
