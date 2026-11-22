"""The Download report (PDF) button of the Tests tab (Fix G5, F3).

The report is read from saved results only (agents/da_test_report_view). The button id carries
`<request id>/<build number>`; no new tab opens.
"""

from dash import ALL, Input, Output, ctx, dcc
from dash.exceptions import PreventUpdate

from agents.da_test_report_pdf import pdf_file_name, report_pdf
from agents.da_test_report_view import get_report
from callbacks.screen_callbacks.da_developer_assistant_page_callbacks import get_settings
from layouts.da_build_panel import REPORT_DOWNLOAD_TYPE
from layouts.da_developer_assistant_page import REPORT_FILE_ID


def pdf_download(settings, index: str):
    """The dcc.Download data for one report, or None when there is no saved report."""
    request_id, _, number = (index or "").rpartition("/")
    if not request_id or not number.isdigit():
        return None
    report = get_report(settings, request_id, int(number))
    if report is None:
        return None
    return dcc.send_bytes(report_pdf(report), pdf_file_name(request_id, int(number)))


def register_da_test_report_page_callbacks(app) -> None:
    @app.callback(
        Output(REPORT_FILE_ID, "data"),
        Input({"type": REPORT_DOWNLOAD_TYPE, "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def download(_clicks):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        return pdf_download(get_settings(), trigger["index"])
