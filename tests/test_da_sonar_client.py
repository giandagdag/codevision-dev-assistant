"""SonarQube read-only client and snapshot (fix 11-2, AG-11 to AG-13). Fake session, no network."""

import json
import logging
from dataclasses import replace

import pytest
from dash.exceptions import PreventUpdate

from agents.da_admin_sonar import load_snapshot, refresh_snapshot, sample_with_mapping, source_pill
from agents.da_sonar_client import SonarError, fetch_active_rules
from callbacks.screen_callbacks.da_admin_page_callbacks import sonar_refresh_action

TOKEN = "squ_made_up_token_123"


class FakeReply:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, token_ok=True, total=3):
        self.calls = []
        self.token_ok = token_ok
        self.total = total

    def get(self, url, params=None, auth=None, timeout=None):
        self.calls.append((url, params, auth, timeout))
        if not self.token_ok:
            return FakeReply(401)
        if url.endswith("/api/qualityprofiles/search"):
            return FakeReply(body={"profiles": [{"key": "k1", "name": "Mine", "isDefault": True}]})
        page = params["p"]
        rules = [{"key": f"py:S{n}", "name": f"Rule {n}", "severity": "MAJOR"} for n in range(3)]
        # 2 pages: page size is 500, so claim a total that needs two pages
        body = {"rules": rules[: 2 if page == 1 else 1], "total": 501 if page == 1 else 3}
        return FakeReply(body=body)


@pytest.fixture
def sonar_settings(make_settings):
    return make_settings(sonar_url="https://sonar.example.test", sonar_token=TOKEN)


@pytest.fixture(autouse=True)
def index_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))
    return tmp_path


def test_ag11_empty_settings_keep_sample(make_settings):
    settings = make_settings()
    assert "Not connected" in refresh_snapshot(settings)
    assert load_snapshot() is None
    assert source_pill(None) == "Sample list"
    assert sample_with_mapping({})[0]["key"]  # the sample still shows


def test_ag12_two_pages_saved_with_severity(sonar_settings, index_folder):
    session = FakeSession()
    message = refresh_snapshot(sonar_settings, session=session)
    assert message == "Saved 3 rules from SonarQube."
    snapshot = load_snapshot()
    assert [r["severity"] for r in snapshot["rules"]] == ["MAJOR"] * 3
    assert source_pill(snapshot).startswith("From SonarQube, ")
    assert session.calls[0][2] == (TOKEN, "")  # token as user name, empty password
    assert all(call[3] == 15 for call in session.calls)
    mapped = sample_with_mapping({"MAJOR": "should_fix"})
    assert mapped[0]["mapped"] == "should_fix"


def test_ag13_refused_token_keeps_old_list_and_never_logs_token(sonar_settings, caplog):
    first = load_snapshot()
    with caplog.at_level(logging.DEBUG):
        message = refresh_snapshot(sonar_settings, session=FakeSession(token_ok=False))
    assert message == "The token was refused"
    assert load_snapshot() == first
    assert TOKEN not in caplog.text
    assert TOKEN not in repr(sonar_settings)


def test_old_list_stays_after_failed_refresh(sonar_settings, index_folder):
    refresh_snapshot(sonar_settings, session=FakeSession())
    before = (index_folder / "da_sonar_rules.json").read_text(encoding="utf-8")
    refresh_snapshot(sonar_settings, session=FakeSession(token_ok=False))
    assert (index_folder / "da_sonar_rules.json").read_text(encoding="utf-8") == before
    assert json.loads(before)["profile"] == "Mine"


def test_profile_not_found(sonar_settings):
    with pytest.raises(SonarError, match="Profile not found"):
        fetch_active_rules(replace(sonar_settings, sonar_profile="Other"), FakeSession())


def test_refresh_button_needs_a_click_and_admin(make_settings):
    with pytest.raises(PreventUpdate):
        sonar_refresh_action(make_settings(developer_id="dev-0001"), 1)
