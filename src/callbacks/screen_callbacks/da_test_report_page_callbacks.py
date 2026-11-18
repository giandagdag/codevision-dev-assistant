"""Wires the test report page (Fix D1 spec E9): show it, print it, download it.

The report is read from saved results only (agents/da_test_report_view). A bad or unknown path
shows a plain sentence, never a Dash error page.
"""

from dash import Input, Output, State, dcc

from agents.da_test_report import report_file_name
from agents.da_test_report_view import get_report
from callbacks.screen_callbacks.da_developer_assistant_page_callbacks import get_settings
from db_table_functions.da_db import DatabaseBusyError
from layouts.da_test_report_page import (
    NO_REPORT_TEXT,
    REPORT_BODY_ID,
    REPORT_DOWNLOAD_ID,
    REPORT_FILE_ID,
    REPORT_PRINT_ID,
    REPORT_SHELL_ID,
    parse_report_path,
    report_document,
    report_html,
)

LOCATION_ID = "url"


def report_text(settings, pathname: str | None) -> str:
    """The html text for this path, or a sentence when there is no report."""
    wanted = parse_report_path(pathname)
    if wanted is None:
        return ""
    try:
        report = get_report(settings, *wanted)
    except DatabaseBusyError as error:
        return str(error)
    return report_html(report) if report else NO_REPORT_TEXT


def register_da_test_report_page_callbacks(app) -> None:
    @app.callback(
        Output(REPORT_SHELL_ID, "style"),
        Output(REPORT_BODY_ID, "children"),
        Input(LOCATION_ID, "pathname"),
    )
    def show_report(pathname):
        if parse_report_path(pathname) is None:
            return {"display": "none"}, ""
        return {}, report_text(get_settings(), pathname)

    @app.callback(
        Output(REPORT_FILE_ID, "data"),
        Input(REPORT_DOWNLOAD_ID, "n_clicks"),
        State(LOCATION_ID, "pathname"),
        prevent_initial_call=True,
    )
    def download(_clicks, pathname):
        wanted = parse_report_path(pathname)
        report = get_report(get_settings(), *wanted) if wanted else None
        if report is None:
            return None
        return dcc.send_string(report_document(report), report_file_name(*wanted))

    app.clientside_callback(
        "function(n){ if(n){ window.print(); } return window.dash_clientside.no_update; }",
        Output(REPORT_SHELL_ID, "title"),  # never changes: the function only prints
        Input(REPORT_PRINT_ID, "n_clicks"),
        prevent_initial_call=True,
    )
