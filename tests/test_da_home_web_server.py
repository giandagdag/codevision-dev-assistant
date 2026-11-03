from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests.da_tree import all_text, components
from web import da_home_web_server as server


def make_app(make_settings, monkeypatch, published=True):
    settings = make_settings()
    monkeypatch.setattr(server, "get_settings", lambda: settings)
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return server.create_app()


def test_the_app_builds_and_serves_its_pages(make_settings, published_rulebook, monkeypatch):
    app = make_app(make_settings, monkeypatch)
    client = app.server.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/_dash-layout").status_code == 200
    assert client.get("/_dash-dependencies").status_code == 200


def test_menu_has_only_the_developer_assistant(make_settings, published_rulebook, monkeypatch):
    app = make_app(make_settings, monkeypatch)
    links = components(app.layout, "NavLink")
    assert [link.label for link in links] == ["Developer Assistant"]
    assert links[0].active is True
    assert "dev-home-01" in all_text(app.layout)


def test_the_shell_has_a_location_for_the_page(make_settings, published_rulebook, monkeypatch):
    app = make_app(make_settings, monkeypatch)
    ids = [getattr(c, "id", None) for c in components(app.layout)]
    assert "url" in ids and "da-page-content" in ids


def test_it_listens_on_this_computer_only(make_settings, published_rulebook, monkeypatch, capsys):
    # Rule R13. Nothing is started: Dash's run is replaced.
    calls = {}
    monkeypatch.setattr(
        server.Dash, "run", lambda self, **kwargs: calls.update(kwargs), raising=True
    )
    make_app(make_settings, monkeypatch)
    assert server.main() == 0
    assert calls["host"] == "127.0.0.1" and calls["debug"] is False


def test_it_tells_you_to_run_the_loader_when_no_rulebook_exists(make_settings, monkeypatch, capsys):
    make_app(make_settings, monkeypatch)
    assert server.main() == 1
    assert "da_load_starter_rulebook.py" in capsys.readouterr().out


def test_start_up_pauses_a_build_that_was_running_when_the_server_stopped(
    make_settings, published_rulebook, monkeypatch, capsys
):
    """Row 6-27 at the real start-up path."""
    from agents import da_build_flow as build_flow
    from tests.da_build_play import ready_with_workspace

    monkeypatch.setattr(server.Dash, "run", lambda self, **kwargs: None, raising=True)
    settings = make_settings()
    request_id, _ = ready_with_workspace(settings)
    build_flow.start_build(settings, request_id, 0)  # marked running, but no thread: a restart
    monkeypatch.setattr(server, "get_settings", lambda: settings)

    assert server.main() == 0

    state = build_flow.get_state(settings, request_id)
    assert (state.step, state.message) == ("b_interrupted", build_flow.SERVER_RESTART_MESSAGE)
    assert request_id in capsys.readouterr().out
