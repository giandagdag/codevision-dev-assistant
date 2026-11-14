"""The Workspace on screen (spec sections 3 and 9): the header chip, the Build tab, and the
stores the browser script talks through.

Presentation only (rule R12), like the other layout files: it turns what the Workspace flow
already decided into components. Nothing here judges a folder or a file.
"""

import dash_mantine_components as dmc
from dash import dcc

from pydantic_classes.da_workspace_models import CheckResult, WorkspaceView
from styles import da_styles
from web import da_web_components as parts

# Browser-run buttons (the JavaScript starts these) use their own id type.
WS_BTN_TYPE = "da-ws-btn"
# The hand-over points between the browser and the server (see da_workspace_callbacks.py).
WS_CTX_ID = "da-ws-ctx"
WS_EVENT_ID = "da-ws-event"
WS_JOB_ID = "da-ws-job"
WS_REPORT_ID = "da-ws-report"
WS_PACK_ID = "da-ws-pack"
WS_SINK_ID = "da-ws-sink"  # a store the ZIP callback writes to; it holds nothing
WS_PERM_OK_ID = "da-ws-perm-ok"
WS_PERM_NEEDS_ID = "da-ws-perm-needs"
WS_BUSY_TEXT = "⏳ Checking your folder…"
NOT_CODEVISION = "Not a CodeVision folder"
RECONNECT_KEY = "reconnect"
USE_KEY = "use_remembered"
USE_LABEL = "Use remembered folder"

STATUS_OUTCOME_TEXT = {
    "Not written yet": "Not written yet",
    "Written": "Written",
    "Changed by you": "Changed by you",
    "Missing": "Missing",
    "Created": "Created",
}
ACTION_TEXT = {"create": "New", "modify": "Change"}


def workspace_context(
    view: WorkspaceView, build=None, restore_build: int = 0, handoff_revision: int = 0
) -> dict:
    """What the browser script needs for a click: the plan's paths, the policy and the revision.
    With a BuildView it also carries what the Build clicks and the automatic write need.
    `restore_build` (Phase 8): the build the Restore button would put back, 0 when none."""
    context = {
        "request_id": view.request.request_id,
        "ws_revision": view.revision,
        "planned_paths": view.planned_paths,
        "markers": view.markers,
        "max_file_kb": view.max_file_kb,
        "step": view.step,
        "mode": view.mode,
        "folder_name": view.folder_name,
        "build_revision": 0,
        "build_step": "start",
        "auto_write": False,
        "restore_build": restore_build,
        "handoff_revision": handoff_revision,
    }
    if build is not None:
        context["build_revision"] = build.revision
        context["build_step"] = build.state.step
        context["auto_write"] = build.auto_write
    return context


def workspace_stores(
    view: WorkspaceView, build=None, restore_build: int = 0, handoff_revision: int = 0
) -> list:
    """The store that tells the browser script where the request stands (revision, plan paths).
    It is redrawn with the page, so it always holds the current values."""
    context = workspace_context(view, build, restore_build, handoff_revision)
    return [dcc.Store(id=WS_CTX_ID, data=context)]


def workspace_hop_stores() -> list:
    """The hand-over stores of the four-hop chain. They are drawn ONCE, with the page itself.

    Why: a Dash memory store that is drawn again gets its old value back and announces it as a
    change. Redrawn after every step, an old "facts" event would start the whole chain again
    and again (found in the real-browser test). Drawn once, they only change when a click does.
    """
    return [
        dcc.Store(id=WS_EVENT_ID),
        dcc.Store(id=WS_JOB_ID),
        dcc.Store(id=WS_REPORT_ID),
        dcc.Store(id=WS_PACK_ID),
        dcc.Store(id=WS_SINK_ID),
    ]


def ws_button_id(key: str, where: str) -> dict:
    """A browser-run button's id. `where` (chip or bar) keeps two buttons with the same key from
    sharing one id, which Dash cannot tell apart."""
    return {"type": WS_BTN_TYPE, "index": key, "where": where}


def _blocked_by_folder(check: CheckResult | None) -> bool:
    return check is not None and any(item.code in ("B1", "B2") for item in check.blockers)


def workspace_chip(view: WorkspaceView) -> dmc.Group:
    """The header chip (spec section 3). It shows STATUS ONLY: the folder name and its state. It
    has no buttons; Change folder and Reconnect are buttons under the chat (work test, P30)."""
    if view.mode == "download" and view.step in ("ws_fallback", "ws_ready", "ws_blocked"):
        return dmc.Group([dmc.Text("📁 Download mode", size="sm", fw=600)], gap=6, id="da-ws-chip")
    if not view.folder_name or view.step == "start":
        return dmc.Group(
            [dmc.Text("📁 No workspace chosen", size="sm", c=da_styles.MUTED)],
            gap=6,
            id="da-ws-chip",
        )
    name = dmc.Text(f"📁 {view.folder_name}", size="sm", fw=600)
    if _blocked_by_folder(view.check):
        return dmc.Group(
            [name, dmc.Text(f"⚠️ {NOT_CODEVISION}", size="sm", c="orange")], gap=6, id="da-ws-chip"
        )
    # The browser decides which of the next two is shown (it alone knows if permission is still
    # there; W4). Until it answers, the "needs your OK" variant stays hidden.
    ready = dmc.Text("✅", size="sm", id=WS_PERM_OK_ID)
    needs = dmc.Text(
        "Needs your OK", size="sm", c="orange", id=WS_PERM_NEEDS_ID, style={"display": "none"}
    )
    return dmc.Group([name, ready, needs], gap=6, id="da-ws-chip")


def build_panel(view: WorkspaceView) -> list:
    """The Build tab before a build starts (spec section 9): the workspace panel. The Build button
    is under the chat; once a build has started, da_build_panel draws the tab."""
    checked = _short_time(view.checked_at) if view.checked_at else "not yet"
    mode_note = " (download mode)" if view.mode == "download" else ""
    lines: list = [
        dmc.Text(
            f"Workspace: {view.folder_name or 'none'}{mode_note}. Checked {checked}.",
            size="sm",
            id="da-ws-summary",
        ),
        _file_table(view),
    ]
    if view.check and view.check.info:
        lines += [dmc.Text(text, size="xs", c=da_styles.MUTED) for text in view.check.info]
    if view.last_scan is not None:
        lines.append(_scan_block(view))
    return [dmc.Stack(lines, gap="sm")]


def _short_time(moment) -> str:
    """Singapore time as the spec writes it: 1 Nov, 15:40 (stored UTC)."""
    local = moment.astimezone(parts.SINGAPORE_TIME)
    return f"{local.day} {local:%b}, {local:%H:%M}"


def _file_table(view: WorkspaceView) -> dmc.Table:
    head = dmc.TableThead(
        dmc.TableTr(
            [dmc.TableTh(text) for text in ("File", "Action", "Status", "Baseline taken")]
        )
    )
    body = []
    for row in view.rows:
        baseline = parts.format_singapore_time(row.baseline_at) if row.baseline_at else ""
        body.append(
            dmc.TableTr(
                [
                    dmc.TableTd(dmc.Text(row.path, size="xs", ff="monospace")),
                    dmc.TableTd(dmc.Text(ACTION_TEXT[row.action], size="xs")),
                    dmc.TableTd(dmc.Text(row.status, size="xs")),
                    dmc.TableTd(dmc.Text(baseline, size="xs", c=da_styles.MUTED)),
                ]
            )
        )
    return dmc.Table([head, dmc.TableTbody(body)], id="da-ws-files", withTableBorder=True)


def _scan_block(view: WorkspaceView) -> dmc.Box:
    labels = {
        "unchanged": "Unchanged",
        "changed": "Changed by you",
        "missing": "Missing",
    }
    items = [
        dmc.Text(f"{labels[item.outcome]}: {item.path}", size="xs", ff="monospace")
        for item in view.last_scan.items
        if item.outcome != "unchanged"
    ] or [dmc.Text("No changes found at the last re-scan.", size="xs", c=da_styles.MUTED)]
    return dmc.Box(
        [dmc.Text("Last re-scan", fw=700, size="sm", c=da_styles.NAVY), *items], id="da-ws-scan"
    )
