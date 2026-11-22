"""Fix G5 F3: the Tests tab downloads the saved report as one PDF (no page, no new tab)."""

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents.da_test_report_view import get_report
from callbacks.screen_callbacks.da_admin_page_callbacks import developer_page_style
from callbacks.screen_callbacks.da_test_report_page_callbacks import pdf_download
from tests.da_build_play import ready_with_workspace

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def built(make_settings):
    settings = make_settings()
    request_id = ready_with_workspace(settings)[0]
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    loop.run_build(settings, request_id)
    return settings, request_id


def test_g5_20_the_button_gives_one_pdf_file_with_every_test_id(built):
    settings, request_id = built
    sent = pdf_download(settings, f"{request_id}/1")

    assert sent["filename"] == f"{request_id}-build-1-test-report.pdf"
    assert sent["base64"] is True  # dcc.send_bytes
    from base64 import b64decode

    data = b64decode(sent["content"])
    assert data.startswith(b"%PDF-") and b"startxref" in data
    for section in get_report(settings, request_id, 1)["sections"]:
        for row in section["rows"]:
            assert row["id"].encode() in data


def test_a_build_with_no_saved_report_downloads_nothing(built):
    settings, request_id = built

    assert get_report(settings, request_id, 99) is None
    assert pdf_download(settings, f"{request_id}/99") is None
    assert pdf_download(settings, "garbage") is None


def test_the_old_report_address_is_no_longer_a_page():
    assert developer_page_style("/dev-assistant/report/CVDA-0001/3") == {}
