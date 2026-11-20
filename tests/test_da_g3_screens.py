"""Fix G3 step 3: the screens say which Python runs the tests, never its path (G3-9, T6)."""

import dataclasses
import sys

import pytest

from agents import da_build_flow as flow
from agents import da_sandbox_python
from agents.da_admin_overview import server_settings_view
from layouts import da_build_panel as panel
from tests.da_build_play import ready_with_workspace
from tests.da_tree import all_text

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def fake_python(tmp_path, monkeypatch):
    path = tmp_path / "secret_folder" / "python.exe"
    path.parent.mkdir()
    path.write_text("x")
    monkeypatch.setattr(da_sandbox_python, "_probe", lambda p, args: "3.14.2")
    da_sandbox_python._versions.clear()
    return str(path)


def test_g3_9_the_build_tab_names_codevisions_python_without_a_path(make_settings, fake_python):
    settings = dataclasses.replace(make_settings(), codevision_python=fake_python)
    request_id = ready_with_workspace(settings)[0]

    text = all_text(panel.build_tab(flow.get_build_view(settings, request_id)))

    assert "Tests run with: CodeVision's Python 3.14.2" in text
    assert "secret_folder" not in text and "python.exe" not in text


def test_g3_9_without_the_setting_it_names_this_apps_python(make_settings):
    settings = make_settings()
    request_id = ready_with_workspace(settings)[0]

    text = all_text(panel.build_tab(flow.get_build_view(settings, request_id)))

    version = ".".join(map(str, sys.version_info[:3]))
    assert f"Tests run with: Developer Assistant's Python {version}" in text
    assert sys.executable not in text


def test_g3_9_a_python_that_cannot_be_used_draws_no_line(make_settings, tmp_path):
    settings = dataclasses.replace(make_settings(), codevision_python=str(tmp_path / "nope.exe"))
    request_id = ready_with_workspace(settings)[0]

    view = flow.get_build_view(settings, request_id)

    assert view.tests_run_with == ""
    assert "Tests run with" not in all_text(panel.build_tab(view))


def test_t6_the_admin_settings_list_shows_tests_run_with(make_settings, fake_python, tmp_path):
    set_up = dataclasses.replace(make_settings(), codevision_python=fake_python)
    shown = dict(server_settings_view(set_up))
    assert shown["Tests run with"] == "CodeVision's Python 3.14.2"

    gone = dataclasses.replace(make_settings(), codevision_python=str(tmp_path / "nope.exe"))
    assert "does not exist" in dict(server_settings_view(gone))["Tests run with"]
    assert "Tests run with" in dict(server_settings_view(make_settings()))
