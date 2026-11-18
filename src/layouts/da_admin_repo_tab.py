"""Repository and index tab: connection, refresh, exclusions, folders, index health."""

from datetime import datetime

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_index import read_health, recent_runs
from agents.da_admin_labels import label as field_label
from agents.da_admin_rebuild import running_since
from layouts.da_admin_build_tab import _number_field
from layouts.da_admin_common import (
    TAB_REPO,
    TEXT_COLUMN,
    _draft,
    _text_rows,
    list_table,
    two_columns,
    version_pill,
    word_chips,
)
from layouts.da_admin_common import section as _section
from layouts.da_admin_index_panels import (
    REFRESH_MODES,
    fixed_skip_rows,
    health_tiles,
    index_pill,
    rebuild_controls,
    recent_refreshes,
    refresh_tiles,
)
from pydantic_classes.da_rulebook_models import Policy, RulebookVersion

# --- Repository and index (Phase 11c, spec 11) ---

REPO_LIST_TABLES = (
    ("allowed_folders", "Allowed folders"),
    ("workspace_markers", "Workspace markers"),
)
REPO_PATTERN = "new_file_name_pattern"
REPO_SIZE = "workspace_max_file_kb"


def repo_view(
    version: RulebookVersion,
    server: list[tuple[str, str]] | None,
    editable: bool = False,
    draft: dict | None = None,
    active: bool = True,
    ask_rebuild: bool = False,
):
    """Read-only server settings, then the four editable fields. `server` is (name, shown value)."""
    policy = version.rulebook.policy
    settings_lines = [
        dmc.Text(f"{field_label(name)}: {value}", size="sm") for name, value in (server or [])
    ]
    pattern = _draft(draft, REPO_PATTERN, policy.new_file_name_pattern)
    if editable:
        pattern_widget = dmc.TextInput(
            label="New file name pattern (a regular expression)",
            value=pattern,
            id={"type": "adm-field", "tab": TAB_REPO, "name": REPO_PATTERN},
            size="xs",
        )
    else:
        pattern_widget = dmc.Text(f"New file name pattern: {pattern}", size="sm")
    health = read_health()
    left = [
        _section("Connection", _connection(policy, editable, draft)),
        _section(
            "Refresh",
            refresh_tiles(
                _draft(draft, "index_refresh_mode", policy.index_refresh_mode),
                _draft(draft, "index_nightly_time", policy.index_nightly_time),
            ),
        ),
        _section(
            "Exclusions",
            dmc.Stack(
                [
                    fixed_skip_rows(),
                    list_table(
                        TAB_REPO,
                        "index_exclusions",
                        EXCLUSION_COLUMNS,
                        _draft(draft, "index_exclusions", _exclusion_rows(policy)),
                        editable,
                        kinds={"kind": list(EXCLUSION_KINDS)},
                    ),
                ]
            ),
        ),
        *[
            _section(title, _repo_list(table, policy, editable, draft))
            for table, title in REPO_LIST_TABLES
        ],
        _section("New file name pattern", pattern_widget),
        _section(
            "Largest file the laptop scan reads",
            _number_field(policy, REPO_SIZE, editable, draft, TAB_REPO),
        ),
        dmc.Accordion(
            [
                dmc.AccordionItem(
                    [
                        dmc.AccordionControl("Server settings (read only, set in .env)"),
                        dmc.AccordionPanel(dmc.Stack(settings_lines, gap=2)),
                    ],
                    value="server",
                )
            ],
            value=None,
        ),
    ]
    right = [
        _section("Index health", health_tiles(health)),
        _section("Recent refreshes", recent_refreshes(recent_runs())),
    ]
    return html.Div(
        [
            version_pill(version, active),
            index_pill(health, datetime.now()),
            rebuild_controls(running_since(), recent_runs(), ask_rebuild),
            two_columns(html.Div(left), html.Div(right)),  # spec 7: connection left, health right
        ]
    )


def _repo_list(table: str, policy: Policy, editable: bool, draft: dict | None):
    """Allowed folders and markers: chips to read, a table to edit."""
    words = _draft(draft, table, getattr(policy, table))
    if not editable:
        return word_chips(words)
    return list_table(TAB_REPO, table, (TEXT_COLUMN,), _text_rows(words), True)


EXCLUSION_COLUMNS = ("pattern", "reason", "kind")
EXCLUSION_KINDS = ("Config", "Build", "Scratch")


def _exclusion_rows(policy: Policy) -> list[dict]:
    return [e.model_dump() for e in policy.index_exclusions]


def _connection(policy: Policy, editable: bool, draft: dict | None):
    scope = _draft(draft, "index_folder_scope", policy.index_folder_scope)
    lines = [
        dmc.Text(f"Bitbucket repository: {policy.index_repo or '(not set)'}", size="sm"),
        dmc.Text(f"Branch indexed: {policy.index_branch} 🔒", size="sm"),
    ]
    if editable:
        lines.append(
            dmc.TextInput(
                label="Folder scope (empty = the server's default source folder)",
                value=scope,
                id={"type": "adm-field", "tab": TAB_REPO, "name": "index_folder_scope"},
                size="xs",
            )
        )
        lines.append(
            dmc.Select(
                label="Refresh",
                data=[
                    {"value": k, "label": t, "disabled": k == "merge"} for k, t, _ in REFRESH_MODES
                ],
                value=_draft(draft, "index_refresh_mode", policy.index_refresh_mode),
                id={"type": "adm-field", "tab": TAB_REPO, "name": "index_refresh_mode"},
                size="xs",
            )
        )
        lines.append(
            dmc.TextInput(
                label="Nightly time (Singapore time, 24-hour HH:MM)",
                value=_draft(draft, "index_nightly_time", policy.index_nightly_time),
                id={"type": "adm-field", "tab": TAB_REPO, "name": "index_nightly_time"},
                size="xs",
            )
        )
    else:
        lines.append(
            dmc.Group([dmc.Text("Folder scope:", size="sm"), dmc.Code(scope or "(default)")], gap=4)
        )
    return dmc.Stack(lines, gap=2)
