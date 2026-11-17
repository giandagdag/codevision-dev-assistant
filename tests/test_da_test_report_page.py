"""Fix D1 step 6: the report page reads a saved build report; print and download use one text."""

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents.da_test_report import report_file_name
from agents.da_test_report_view import get_report
from callbacks.screen_callbacks.da_admin_page_callbacks import developer_page_style
from callbacks.screen_callbacks.da_test_report_page_callbacks import report_text
from layouts.da_test_report_page import (
    NO_REPORT_TEXT,
    PRINT_CSS,
    parse_report_path,
    report_document,
    report_html,
    report_shell,
)
from tests.da_build_play import ready_with_workspace

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def built(make_settings):
    settings = make_settings()
    request_id = ready_with_workspace(settings)[0]
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    loop.run_build(settings, request_id)
    return settings, request_id


def test_the_path_is_read_and_a_bad_one_is_refused():
    assert parse_report_path("/dev-assistant/report/CVDA-0001/3") == ("CVDA-0001", 3)
    for bad in (None, "/inbox", "/dev-assistant/report/x", "/dev-assistant/report/x/y"):
        assert parse_report_path(bad) is None
    assert developer_page_style("/dev-assistant/report/CVDA-0001/3") == {"display": "none"}


def test_d1_9_the_page_shows_header_summary_sections_and_evidence_without_a_path(built):
    settings, request_id = built
    text = report_text(settings, f"/dev-assistant/report/{request_id}/1")

    assert request_id in text and "Summary" in text and "1. Against the requirement" in text
    assert "<th>Input</th>" in text and "Python" in text
    assert "Users" not in text and "\\" not in text  # no server path


def test_d1_10_download_is_one_offline_file_with_the_same_content(built):
    settings, request_id = built
    report = get_report(settings, request_id, 1)
    document = report_document(report)

    assert report_html(report) in document
    assert "<script" not in document and "http" not in document
    assert report_file_name("CVDA-2026-0001", 1) == "CVDA-2026-0001-build-1-test-report.html"


def test_d1_11_print_styles_hide_the_app_chrome():
    assert "@media print" in PRINT_CSS and "mantine-AppShell-header" in PRINT_CSS
    assert "da-no-print" in PRINT_CSS
    assert "da-no-print" in str(report_shell())  # the buttons carry the class


def test_a_build_with_no_saved_report_says_so(built):
    settings, request_id = built

    assert get_report(settings, request_id, 99) is None
    assert report_text(settings, f"/dev-assistant/report/{request_id}/99") == NO_REPORT_TEXT
