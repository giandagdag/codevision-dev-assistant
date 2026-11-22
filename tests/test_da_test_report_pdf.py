"""Fix G5 F2/F4: the saved report laid out as a PDF."""

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents.da_test_report_pdf import SECTION_COLUMNS, pdf_file_name, report_pdf
from agents.da_test_report_view import get_report
from tests.da_build_play import ready_with_workspace

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def report(make_settings):
    settings = make_settings()
    request_id = ready_with_workspace(settings)[0]
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    loop.run_build(settings, request_id)
    return get_report(settings, request_id, 1)


def test_g5_20_pdf_has_every_test_id_and_the_fixed_columns(report):
    data = report_pdf(report)
    assert data.startswith(b"%PDF-") and b"startxref" in data
    for section in report["sections"]:
        for row in section["rows"]:
            assert row["id"].encode() in data
    for title, _pct in SECTION_COLUMNS:
        assert f"({title})".encode() in data
    assert sum(p for _, p in SECTION_COLUMNS) == 100


def test_file_name_has_no_html():
    assert pdf_file_name("CVDA-2026-0001", 2) == "CVDA-2026-0001-build-2-test-report.pdf"


def test_values_are_cut_and_secrets_hidden(report):
    row = report["sections"][0]["rows"][0]
    row["evidence"] = [{"label": "x", "given": "a" * 900, "expected": "password=hunter2xyz",
                        "actual": "b", "match": True}]  # fmt: skip
    data = report_pdf(report)
    assert b"a" * 501 not in data
    assert b"hunter2xyz" not in data
