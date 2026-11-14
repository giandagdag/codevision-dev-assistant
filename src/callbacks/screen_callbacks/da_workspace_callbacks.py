"""The browser-to-server chain for the Workspace (plan: "how the browser and the server talk").

Four hops, each a Dash callback. The picker only opens right after a click, so hop 1 is
JavaScript straight from the click, with no server call before it:

1. click      (browser)  pick or re-allow the folder, collect FACTS  -> da-ws-event
2. judge      (server)   blocked: save it. Passed: hand back a JOB   -> da-ws-job
3. write      (browser)  run the job with the edit guard             -> da-ws-report
4. save       (server)   ONE write: state, file rows, audit, chat

Re-scan and the upload check end at hop 2 (no write to the laptop). The ZIP goes through
da-ws-pack. Every rule lives in da_workspace_flow and da_workspace_checks (rule R12): this file
only moves data. Like the page callbacks, the functions are at the top so tests can call them.
"""

from dash import ALL, Input, Output, State, no_update
from dash.exceptions import PreventUpdate
from pydantic import ValidationError

from agents import da_build_flow as build_flow
from agents import da_build_runner as build_runner
from agents import da_enhance_flow as enhance_flow
from agents import da_refine_flow as refine_flow
from agents import da_workspace_flow as flow
from callbacks.screen_callbacks.da_handoff_callbacks import final_check_from_facts
from db_table_functions.da_db import DatabaseBusyError
from db_table_functions.db_tbl_da_build import BuildError
from db_table_functions.db_tbl_da_understand import UnderstandError
from layouts.da_developer_assistant_page import BUSY_ID, MESSAGE_ID, REFRESH_ID
from layouts.da_workspace_panel import (
    RECONNECT_KEY,
    USE_KEY,
    WS_BTN_TYPE,
    WS_CTX_ID,
    WS_EVENT_ID,
    WS_JOB_ID,
    WS_PACK_ID,
    WS_PERM_NEEDS_ID,
    WS_PERM_OK_ID,
    WS_REPORT_ID,
    WS_SINK_ID,
    ws_button_id,
)
from pydantic_classes.da_workspace_models import FolderFacts, WriteReport
from web.da_workspace_bridge import clientside_function

SHOWN_ERRORS = (UnderstandError, DatabaseBusyError)
ENHANCE_PREFIX = "enhance_"  # the event kinds of the Phase 9 freshness buttons
UNEXPECTED = "The browser sent something unexpected. Nothing was saved. Please try again."
NOT_CONNECTED = "Your folder is not connected right now. Press Reconnect, then the write runs."

# Hop 1. Called straight from the click, so the browser still allows the picker to open.
CLICK_BODY = """
const trigger = dash_clientside.callback_context.triggered[0];
if (!trigger || !trigger.value) { return window.dash_clientside.no_update; }
const key = JSON.parse(trigger.prop_id.split('.')[0]).index;
return window.daWorkspace.handle(key, ctx).then((result) => ({...result, nonce: Date.now()}));
"""
# Hop 3: run the job the server approved.
WRITE_BODY = """
if (!job) { return window.dash_clientside.no_update; }
return window.daWorkspace.write(job).then((report) => ({...report, nonce: Date.now()}));
"""
# The ZIP download.
DOWNLOAD_BODY = """
if (pack) { window.daWorkspace.download(pack); }
return window.dash_clientside.no_update;
"""
# W4: on a redraw only ASK whether permission is still there. Never prompt without a click.
CHIP_BODY = f"""
const ok = document.getElementById('{WS_PERM_OK_ID}');
const needs = document.getElementById('{WS_PERM_NEEDS_ID}');
const nothing = window.dash_clientside.no_update;
if (!ok || !needs || !ctx || !ctx.folder_name) {{ return [nothing, nothing, nothing]; }}
// The Reconnect button exists only at ws_ready; the chip text is status only.
return window.daWorkspace.chip().then((chip) => {{
    const granted = chip.permission === 'granted';
    const reconnect = ctx.step === 'ws_ready'
        ? (granted ? {{display: 'none'}} : {{}})
        : nothing;
    return granted
        ? [{{}}, {{display: 'none'}}, reconnect]
        : [{{display: 'none'}}, {{}}, reconnect];
}});
"""


# D-B: at the start step, show "Use <name>" if this browser remembers a folder.
USE_BODY = """
const nothing = window.dash_clientside.no_update;
if (!ctx || ctx.step !== 'start') { return [nothing, nothing]; }
return window.daWorkspace.chip().then((chip) => (
    chip.name ? [{}, 'Use ' + chip.name] : [{display: 'none'}, nothing]
));
"""


def handle_workspace_event(settings, event, ctx, refresh):
    """Hop 2. Returns (refresh, job, pack, message)."""
    if not event or not ctx:
        raise PreventUpdate
    request_id, revision = ctx["request_id"], ctx["ws_revision"]
    try:
        return _dispatch(settings, event, request_id, revision, refresh or 0, ctx)
    except ValidationError:
        return no_update, no_update, no_update, UNEXPECTED
    except SHOWN_ERRORS as error:
        # Nothing was written. The message says why.
        return no_update, no_update, no_update, str(error)


def _dispatch(settings, event: dict, request_id: str, revision: int, refresh: int, ctx=None):
    kind = event.get("kind")
    again = refresh + 1
    build_revision = (ctx or {}).get("build_revision", 0)
    if isinstance(kind, str) and kind.startswith(ENHANCE_PREFIX):
        return _dispatch_enhance(settings, event, request_id, again, ctx or {})
    if kind in ("build_facts", "rebuild_facts"):
        # The browser re-scanned the planned files; the server starts (or restarts) the build and
        # hands it to the background runner. The Build page then polls (spec sections 1 and 10).
        facts = FolderFacts.model_validate(event["facts"])
        if kind == "build_facts":
            build_flow.start_build(settings, request_id, build_revision, facts=facts)
        else:
            build_flow.rebuild_after_stop(settings, request_id, facts, build_revision)
        build_runner.submit_build(settings, request_id)
        return again, None, no_update, ""
    if kind == "build_write":
        job = build_flow.prepare_write(settings, request_id, build_revision)
        return no_update, job.model_dump(mode="json") | {"nonce": event["nonce"]}, no_update, ""
    if kind == "build_download":
        job, readme = build_flow.prepare_build_download(settings, request_id, build_revision)
        pack = {
            "files": [{"path": item.path, "text": item.text} for item in job.files],
            "readme_name": flow.README_NAME,
            "readme": readme,
            "nonce": event["nonce"],
        }
        return again, None, pack, ""
    if kind == "handoff_facts":
        # Phase 10: the browser read the planned files for the Handoff final check. Nothing is
        # written to his folder; the server compares the fingerprints with the last test.
        facts = FolderFacts.model_validate(event["facts"])
        final_check_from_facts(settings, request_id, facts, (ctx or {}).get("handoff_revision", 0))
        return again, None, no_update, ""
    if kind == "handoff_cancelled":
        raise PreventUpdate
    refined = _dispatch_refine(settings, event, request_id, again, ctx or {})
    if refined is not None:
        return refined
    if kind == "facts":
        facts = FolderFacts.model_validate(event["facts"])
        judgement = flow.judge_facts(settings, request_id, facts, revision)
        if judgement.job is not None:
            job = judgement.job.model_dump(mode="json") | {"nonce": event["nonce"]}
            return no_update, job, no_update, ""
        return again, None, no_update, ""
    if kind == "scan_facts":
        flow.rescan(settings, request_id, FolderFacts.model_validate(event["facts"]), revision)
    elif kind == "upload_facts":
        facts = FolderFacts.model_validate(event["facts"])
        if flow.get_workspace_view(settings, request_id).step == "ws_ready":
            flow.rescan(settings, request_id, facts, revision)
        else:
            flow.check_uploaded(settings, request_id, facts, revision)
    elif kind == "fallback":
        flow.use_fallback(settings, request_id, event.get("reason", "refused"), revision)
    elif kind == "cancelled":
        flow.picker_cancelled(settings, request_id, revision)
    elif kind == "different_folder":
        flow.different_folder(settings, request_id, revision)
    elif kind == "download":
        package = flow.prepare_download(settings, request_id, revision)
        pack = {
            "files": [{"path": item.path, "text": item.text} for item in package.job.files],
            "readme_name": flow.README_NAME,
            "readme": package.readme,
            "nonce": event["nonce"],
        }
        return again, None, pack, ""
    elif kind != "reconnected":
        raise PreventUpdate
    return again, None, no_update, ""


def _dispatch_enhance(settings, event: dict, request_id: str, again: int, ctx: dict):
    """Phase 9 step 16c: the browser read the confirmed targets in his folder (nothing else, 9-48);
    the server compares them with main. The revision is the Enhance step's, never the workspace's.
    Nothing is written to his folder."""
    kind = event["kind"]
    if kind == "enhance_cancelled":
        raise PreventUpdate  # the picker was closed: nothing to save, nothing to redraw
    facts = FolderFacts.model_validate(event["facts"])
    revision = ctx.get("enhance_revision")
    if kind in ("enhance_check", "enhance_check_again"):
        enhance_flow.run_freshness(settings, request_id, facts.files, revision)
    elif kind in ("enhance_intentional", "enhance_unchecked"):
        which = kind.removeprefix(ENHANCE_PREFIX)
        enhance_flow.override_freshness(settings, request_id, which, facts.files, revision)
    else:
        raise PreventUpdate
    return again, None, no_update, ""


def _dispatch_refine(settings, event: dict, request_id: str, again: int, ctx: dict):
    """The Phase 8 browser buttons (step 16c), or None when the event is not one of them.

    At `b_written` Re-scan (and the folder upload in download mode) is the Refine re-scan: it
    saves his edits as `scanned` rows with the BUILD revision. Restore build N runs the server's
    write job through the same hops as the build's own write; in download mode the ZIP holds the
    set. The build to put back is the one the page drew (`ctx["restore_build"]`), never one the
    browser names."""
    kind = event.get("kind")
    build_revision = ctx.get("build_revision", 0)
    if kind in ("scan_facts", "upload_facts") and ctx.get("build_step") == "b_written":
        facts = FolderFacts.model_validate(event["facts"])
        refine_flow.rescan(settings, request_id, facts, build_revision)
        return again, None, no_update, ""
    if kind not in ("restore_write", "restore_download"):
        return None
    number = ctx.get("restore_build", 0)
    if not number:
        raise BuildError("Pick the build to restore first.")
    if kind == "restore_write":
        job = refine_flow.prepare_restore(settings, request_id, number, build_revision)
        return no_update, job.model_dump(mode="json") | {"nonce": event["nonce"]}, no_update, ""
    job, readme = refine_flow.prepare_restore_download(settings, request_id, number, build_revision)
    pack = {
        "files": [{"path": item.path, "text": item.text} for item in job.files],
        "readme_name": flow.README_NAME,
        "readme": readme,
        "nonce": event["nonce"],
    }
    return again, None, pack, ""


def finish_workspace_write(settings, report, event, ctx, refresh):
    """Hop 4. The browser ran the job. ONE write. Returns (refresh, message)."""
    if not report or not event or not ctx:
        raise PreventUpdate
    try:
        if event.get("kind") == "build_write":
            return _finish_build_write(settings, report, ctx, refresh)
        if event.get("kind") == "restore_write":
            return _finish_restore_write(settings, report, ctx, refresh)
        facts = FolderFacts.model_validate(event["facts"])
        written = WriteReport.model_validate({k: v for k, v in report.items() if k != "nonce"})
        flow.save_check(settings, ctx["request_id"], facts, written, ctx["ws_revision"])
    except ValidationError:
        return no_update, UNEXPECTED
    except SHOWN_ERRORS as error:
        return no_update, str(error)
    return (refresh or 0) + 1, ""


def _finish_restore_write(settings, report, ctx, refresh):
    """Hop 4 of Restore build N: ONE transaction saves the restore (or the stop)."""
    if report.get("not_connected"):
        return no_update, NOT_CONNECTED
    ignore = ("nonce", "not_connected")
    written = WriteReport.model_validate({k: v for k, v in report.items() if k not in ignore})
    refine_flow.save_restore(
        settings,
        ctx["request_id"],
        ctx.get("restore_build", 0),
        written,
        ctx["build_revision"],
        ctx.get("mode") or "picker",
    )
    return (refresh or 0) + 1, ""


def _finish_build_write(settings, report, ctx, refresh):
    """Hop 4 of the automatic write at b_done: the browser ran the build's write job."""
    if report.get("not_connected"):
        return no_update, NOT_CONNECTED  # nothing is saved: this is not a stopped write
    ignore = ("nonce", "not_connected")
    written = WriteReport.model_validate({k: v for k, v in report.items() if k not in ignore})
    build_flow.save_write(
        settings, ctx["request_id"], written, ctx["build_revision"], ctx.get("mode") or "picker"
    )
    return (refresh or 0) + 1, ""


# The automatic write (D-E): once a build is done and the page is open with the folder allowed,
# ask the server for the write job. It never prompts: with no permission it waits for Reconnect.
#
# The event is sent with set_props after a short delay, NOT returned from the callback. Why: a
# returned value would continue the SAME Dash cascade (redraw, auto-write, save, redraw), and
# Dash does not run a callback twice in one cascade, so the final redraw after the save was
# silently skipped (found in the real-browser test). A set_props call starts a new cascade.
AUTO_WRITE_BODY = """
const nothing = window.dash_clientside.no_update;
if (!ctx || !ctx.auto_write || ctx.mode === 'download') { return nothing; }
if (window.__daAutoWrite === ctx.build_revision) { return nothing; }
window.daWorkspace.chip().then((chip) => {
    if (chip.permission !== 'granted') { return; }
    window.__daAutoWrite = ctx.build_revision;
    setTimeout(() => window.dash_clientside.set_props('da-ws-event',
        { data: { kind: 'build_write', nonce: Date.now() } }), 50);
});
return nothing;
"""


def register_da_workspace_callbacks(app, current_settings) -> None:
    """Attach the hops. `current_settings` is called at click time, so tests can replace it."""
    app.clientside_callback(
        clientside_function("clicks, ctx", CLICK_BODY),
        Output(WS_EVENT_ID, "data"),
        Input({"type": WS_BTN_TYPE, "index": ALL, "where": ALL}, "n_clicks"),
        State(WS_CTX_ID, "data"),
        prevent_initial_call=True,
    )
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(WS_JOB_ID, "data"),
        Output(WS_PACK_ID, "data"),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input(WS_EVENT_ID, "data"),
        State(WS_CTX_ID, "data"),
        State(REFRESH_ID, "data"),
        running=[(Output(BUSY_ID, "style"), {"display": "block"}, {"display": "none"})],
        prevent_initial_call=True,
    )(lambda event, ctx, refresh: handle_workspace_event(current_settings(), event, ctx, refresh))
    app.clientside_callback(
        clientside_function("job", WRITE_BODY),
        Output(WS_REPORT_ID, "data"),
        Input(WS_JOB_ID, "data"),
        prevent_initial_call=True,
    )
    app.callback(
        Output(REFRESH_ID, "data", allow_duplicate=True),
        Output(MESSAGE_ID, "children", allow_duplicate=True),
        Input(WS_REPORT_ID, "data"),
        State(WS_EVENT_ID, "data"),
        State(WS_CTX_ID, "data"),
        State(REFRESH_ID, "data"),
        running=[(Output(BUSY_ID, "style"), {"display": "block"}, {"display": "none"})],
        prevent_initial_call=True,
    )(lambda report, event, ctx, refresh: finish_workspace_write(
        current_settings(), report, event, ctx, refresh
    ))
    app.clientside_callback(
        clientside_function("pack", DOWNLOAD_BODY),
        Output(WS_SINK_ID, "data"),
        Input(WS_PACK_ID, "data"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        clientside_function("content, ctx", AUTO_WRITE_BODY),
        Output(WS_SINK_ID, "data", allow_duplicate=True),
        Input("da-page-content", "children"),
        State(WS_CTX_ID, "data"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        clientside_function("content, ctx", USE_BODY),
        Output(ws_button_id(USE_KEY, "bar"), "style"),
        Output(ws_button_id(USE_KEY, "bar"), "children"),
        Input("da-page-content", "children"),
        State(WS_CTX_ID, "data"),
    )
    app.clientside_callback(
        clientside_function("content, ctx", CHIP_BODY),
        Output(WS_PERM_OK_ID, "style"),
        Output(WS_PERM_NEEDS_ID, "style"),
        Output(ws_button_id(RECONNECT_KEY, "bar"), "style"),
        Input("da-page-content", "children"),
        State(WS_CTX_ID, "data"),
    )
