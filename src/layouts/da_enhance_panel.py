"""What the Enhance steps look like (Phase 9 step 16a): card 2 on Home, the candidate table, the
freshness banner and the enhancement summary.

Presentation only (rule R12): every text and every decision comes from the engine
(`da_enhance_flow`, `da_main_source`); nothing here searches, compares or decides. AS400 picture:
the display file for the "find the member" screen; it only says where each field goes.
"""

import dash_mantine_components as dmc
from dash import dcc

from agents.da_approach_flow import HELP_BUTTON
from agents.da_enhance_flow import OVERRIDE_LABELS, EnhanceView
from agents.da_enhance_help import HELP_STATUS
from agents.da_impact import LIMITS_LINE, summary_line
from agents.da_main_source import stale_message
from layouts import da_developer_assistant_page as page
from layouts.da_workspace_panel import WS_CTX_ID, ws_button_id
from pydantic_classes.da_enhance_models import (
    Candidate,
    ImpactResult,
    SafetyCase,
    SafetyNetRow,
    step_label,
)
from pydantic_classes.da_request_record_models import RequestRecord
from styles import da_styles
from web import da_web_components as parts

NOT_IN_CATALOG = "Not in the catalog"
BEST_MATCH = "Best match"
FOUND_BY = {"name": "Name", "meaning": "Meaning", "name+meaning": "Name and meaning"}
FIND_STEP = 1  # the stepper position: Enhance starts where Understand does
NO_CANDIDATES = "Nothing found yet. Type the program name or describe it."
NO_ENHANCEMENT = "Appears once you describe the change"


def render_enhance_workspace(view: EnhanceView, record: RequestRecord | None = None) -> list:
    """The Find and Freshness steps, drawn with the same frame as every other workspace."""
    return page._workspace(
        title="Change an existing program",
        request_id=view.request_id,
        status=view.label or "DRAFT",
        demo_mode=False,
        messages=[parts.chat_bubble(message) for message in view.messages],
        composer=enhance_composer(view),
        panel=[*find_panel(view), *enhancement_summary(record)],
        state={"request_id": view.request_id, "revision": view.revision, "enhance": view.step},
        step=FIND_STEP,
        stores=[dcc.Store(id=WS_CTX_ID, data=enhance_context(view))],
    )


# --- the buttons of each step (16c) ---
# Server-run buttons are (key, label) pairs; the callback looks the key up again from the saved
# request, so an old window or an index with no button behind it is refused (rule R7).
# Browser-run buttons read the target in his folder first (the server never sees his folder).

KEY_FIX = "fix"
KEY_UNDERSTAND = "understand"
KEY_HELP = "help"
KEY_PICK = "pick"
PICK_SEPARATOR = "|"
KEY_CONTINUE = "continue"
KEY_TRY_AGAIN = "try_again"
CONTINUE_LABEL = "Continue to Approach"
TRY_AGAIN_LABEL = "Try again"
CORRECT_LABEL = "Correct something"  # the Send button at s_review: the text is his correction
UNDERSTAND_LABEL = "Describe the change"
FIX_LABEL = "This is a fix"
BROWSER_PREFIX = "enhance_"
CHECK_KEY = BROWSER_PREFIX + "check"
BROWSER_LABELS = {
    CHECK_KEY: "Check against main",
    BROWSER_PREFIX + "check_again": "I've updated, check again",
    BROWSER_PREFIX + "intentional": OVERRIDE_LABELS["intentional"],
    BROWSER_PREFIX + "unchecked": OVERRIDE_LABELS["unchecked"],
}
DEFAULT_MAX_FILE_KB = 512


def pick_key(path: str, capability: str) -> str:
    return PICK_SEPARATOR.join((KEY_PICK, path, capability))


def enhance_buttons(view: EnhanceView) -> list[tuple[str, str]]:
    """The server-run buttons of the step, in the order they are drawn."""
    buttons: list[tuple[str, str]] = []
    if view.step == "e_pick" and not view.targets:
        for item in view.candidates:
            if item.capability:
                buttons.append((pick_key(item.path, ""), f"Yes, that's it: {item.path}"))
                continue
            # Not in the catalog: he must pick a capability, one button each (spec section 4).
            for name in view.capability_names:
                buttons.append((pick_key(item.path, name), f"{item.path}: it belongs to {name}"))
        if view.kind != "fix":
            buttons.append((KEY_FIX, FIX_LABEL))
    if view.step == "e_fresh" and not view.understand_started:
        buttons.append((KEY_UNDERSTAND, UNDERSTAND_LABEL))
    if view.step == "s_review":
        buttons.append((KEY_CONTINUE, CONTINUE_LABEL))
    if view.step == "s_unable":
        buttons.append((KEY_TRY_AGAIN, TRY_AGAIN_LABEL))
    if view.step in HELP_STATUS:
        buttons.append((KEY_HELP, HELP_BUTTON))
    return buttons


def browser_buttons(view: EnhanceView) -> list[tuple[str, str]]:
    """The buttons that read his folder first: the freshness check and the stale choices."""
    if view.step == "e_pick" and view.targets:
        return [(CHECK_KEY, BROWSER_LABELS[CHECK_KEY])]
    if view.step == "e_stale":
        return [
            (BROWSER_PREFIX + option, BROWSER_LABELS[BROWSER_PREFIX + option])
            for option in view.stale_options
        ]
    return []


def enhance_composer(view: EnhanceView):
    """Text to search at e_find and e_pick; locked choices at the other steps."""
    buttons = enhance_buttons(view)
    if view.step in ("e_find", "e_pick"):
        composer = page._composer(
            "choices" if buttons else "text",
            [label for _key, label in buttons],
            False,
            "",
            send_label="Search",
            typing_prompt="Name the program or describe it, then press Search"
            if buttons
            else "",
        )
    elif view.step == "s_review":
        composer = page._composer(
            "choices",
            [label for _key, label in buttons],
            False,
            "",
            send_label=CORRECT_LABEL,
            typing_prompt="Tell me what to correct, then press Correct something",
        )
    else:
        composer = page._composer(
            "choices", [label for _key, label in buttons], False, ""
        )
    browser = browser_buttons(view)
    if not browser:
        return composer
    bar = dmc.Group(
        [
            parts.choice_button(label, ws_button_id(key, "bar"), parts.PRIMARY)
            for key, label in browser
        ],
        mt="xs",
        mb="xs",
    )
    return dmc.Box([bar, composer])


def enhance_context(view: EnhanceView) -> dict:
    """What the browser script needs: the confirmed targets (the only files it may read, 9-48)
    and the revision of this step. No marker folders: Enhance does not judge his folder."""
    return {
        "request_id": view.request_id,
        "ws_revision": view.revision,
        "enhance_revision": view.revision,
        "planned_paths": [target.path for target in view.targets],
        "markers": [],
        "max_file_kb": DEFAULT_MAX_FILE_KB,
        "step": view.step,
        "mode": "picker",
        "folder_name": "",
        "build_revision": 0,
        "build_step": "start",
        "auto_write": False,
        "restore_build": 0,
    }


def find_panel(view: EnhanceView) -> list:
    """Candidate table, confirmed programs, and the freshness banner when there is a result."""
    sections = [parts.panel_section("Programs found", [candidate_table(view.candidates)])]
    if view.step == "e_pick" and not view.targets and len(view.candidates) > 1:
        sections.append(multi_pick(view))
    if view.targets:
        lines = [
            dmc.Text(
                f"{item.path}: {item.capability}"
                + (f" (senior: {item.named_senior})" if item.named_senior else "")
                + ("" if item.capability_confirmed else " (not yet confirmed by Admin)"),
                size="sm",
            )
            for item in view.targets
        ]
        sections.append(parts.panel_section("Confirmed program", lines))
    banner = freshness_banner(view)
    if banner is not None:
        sections.append(banner)
    return sections


PICK_GROUP_ID = "da-pick-group"
PICK_CONFIRM_ID = "da-pick-confirm"
PICK_CONFIRM_LABEL = "Yes, these are the programs"
CAP_TYPE = "da-cap-pick"  # pattern id: the capability dropdown of a program not in the catalog
CAP_NONE_VALUE = "none"


def multi_pick(view: EnhanceView):
    """Tick more than one program (D-C). The Best match starts ticked. A program not in the catalog
    gets a capability dropdown. The engine checks the paths, the count and the picks (R12)."""
    ticked = [item.path for item in view.candidates if item.best_match]
    caps = [
        dmc.Select(
            id={"type": CAP_TYPE, "index": item.path},
            label=f"{item.path}: capability",
            data=[{"value": CAP_NONE_VALUE, "label": "Pick a capability"}]
            + [{"value": name, "label": name} for name in view.capability_names],
            value=CAP_NONE_VALUE,
            allowDeselect=False,
            size="xs",
        )
        for item in view.candidates
        if not item.capability
    ]
    return parts.panel_section(
        "Change more than one program?",
        [
            dmc.CheckboxGroup(
                id=PICK_GROUP_ID,
                value=ticked,
                children=dmc.Stack(
                    [dmc.Checkbox(label=item.path, value=item.path) for item in view.candidates]
                ),
            ),
            *caps,
            dmc.Button(PICK_CONFIRM_LABEL, id=PICK_CONFIRM_ID, variant="light", mt="xs"),
        ],
    )


def candidate_table(candidates: list[Candidate]):
    if not candidates:
        return dmc.Text(NO_CANDIDATES, c=da_styles.MUTED, size="sm")
    head = dmc.TableThead(
        dmc.TableTr(
            [dmc.TableTh(name) for name in ("Program", "Found by", "Capability", "Named senior")]
        )
    )
    rows = [
        dmc.TableTr(
            [
                dmc.TableTd(_program_cell(item)),
                dmc.TableTd(FOUND_BY[item.how_found]),
                dmc.TableTd(item.capability or NOT_IN_CATALOG),
                dmc.TableTd(item.named_senior or "-"),
            ]
        )
        for item in candidates
    ]
    return dmc.Table([head, dmc.TableTbody(rows)], highlightOnHover=True)


def _program_cell(item: Candidate):
    if not item.best_match:
        return dmc.Code(item.path)
    return dmc.Group([dmc.Code(item.path), dmc.Badge(BEST_MATCH, color="green", variant="light")])


def freshness_banner(view: EnhanceView):
    """None before the first check. Green when every file equals main, orange when not."""
    if view.freshness is None:
        return None
    passed = view.freshness.all_equal
    return dmc.Alert(
        stale_message(view.freshness),
        title="Freshness check",
        color="green" if passed else "orange",
        variant="light",
        id="da-freshness-banner",
    )


IMPACT_KIND = {"direct": "Direct", "possible": "Possible", "imports_only": "Imports only"}
MUST_STILL_PASS = "Must still pass"
NET_EMPTY_IMPACT = "Appears after Discover has run."
NET_EMPTY = "No safety net yet. It is written after Discover is confirmed."
NOT_COVERED_TITLE = "Not covered by the safety net, check manually"
ACCEPTED_TITLE = "Accepted in the safety net"


def impact_card(impact: ImpactResult | None):
    """Who calls the functions in scope (spec section 7). None = Discover has not run yet."""
    if impact is None:
        return parts.panel_section("Impact", [dmc.Text(NET_EMPTY_IMPACT, c=da_styles.MUTED)])
    body: list = [dmc.Text(summary_line(impact), size="sm")]
    if impact.rows:
        head = dmc.TableThead(
            dmc.TableTr(
                [dmc.TableTh(n) for n in ("Caller", "Calls", "How sure", "Capability", "Zone")]
            )
        )
        rows = [
            dmc.TableTr(
                [
                    dmc.TableTd(dmc.Code(f"{r.caller_path}:{r.line} {r.caller_function}")),
                    dmc.TableTd(r.function_in_scope),
                    dmc.TableTd(IMPACT_KIND[r.kind]),
                    dmc.TableTd(r.capability or "-"),
                    dmc.TableTd(r.zone or "-"),
                ]
            )
            for r in impact.rows
        ]
        body.append(dmc.Table([head, dmc.TableTbody(rows)], highlightOnHover=True))
        body.append(dmc.Text(f"{impact.more} more not shown.", size="xs") if impact.more else None)
    if impact.users:  # Upgrade G3: 2-level users from the code link graph
        body.append(dmc.Text("From the code links (two levels):", size="sm", fw=600, mt=6))
        body += [
            dmc.Text(
                f"{'Uses it' if u.level == 1 else 'Uses a user'}: {u.module}"
                + (f" ({u.capability})" if u.capability else ""),
                size="xs",
            )
            for u in impact.users
        ]
    body.append(dmc.Text(LIMITS_LINE, size="xs", c=da_styles.MUTED, mt=6))
    return parts.panel_section("Impact", body)


def after_mark(case: SafetyCase) -> str:
    """The "After the change" column: "Must still pass" or "Expected to change (AC-1)"."""
    if case.expected_to_change:
        return f"Expected to change ({case.expected_to_change})"
    return MUST_STILL_PASS


MARK_TYPE = "da-net-mark"  # pattern id of the "After the change" dropdowns (step 18b)
MARK_NONE_VALUE = "none"  # a dropdown cannot hold an empty value; the callback maps it back


def mark_options(criteria: list[str]) -> list[dict]:
    """The choices of one dropdown: "Must still pass", or "Expected to change (AC-n)"."""
    return [{"value": MARK_NONE_VALUE, "label": MUST_STILL_PASS}] + [
        {"value": item, "label": f"Expected to change ({item})"} for item in criteria
    ]


def _after_cell(case: SafetyCase, criteria: list[str] | None):
    """Text, or (while the net is in review) a dropdown he can change."""
    if criteria is None:
        return after_mark(case)
    return dmc.Select(
        id={"type": MARK_TYPE, "index": case.id},
        data=mark_options(criteria),
        value=case.expected_to_change or MARK_NONE_VALUE,
        allowDeselect=False,
        size="xs",
    )


def safety_net_tab(row: SafetyNetRow | None, mark_criteria: list[str] | None = None) -> list:
    """The Safety net tab (spec section 8, step 6): banner, table, and the not-covered card.
    `mark_criteria` (the AC IDs) turns the "After the change" column into dropdowns; None = text."""
    if row is None:
        return [dmc.Text(NET_EMPTY, c=da_styles.MUTED, size="sm")]
    net = row.net
    count = len(net.cases)
    banner = (
        f"Safety net: {count} tests capture today's behaviour. "
        f"All {count} pass on the unchanged code."
        if count
        else "Safety net: no test could be made to pass on today's code."
    )
    sections: list = [dmc.Alert(banner, color="green" if count else "orange", variant="light")]
    if count:
        head = dmc.TableThead(
            dmc.TableTr([dmc.TableTh(n) for n in ("Test", "Today's behaviour", "After the change")])
        )
        rows = [
            dmc.TableTr(
                [
                    dmc.TableTd(dmc.Badge(case.id, variant="light", style=page.ID_BADGE_STYLE)),
                    dmc.TableTd(case.today_behaviour),
                    dmc.TableTd(_after_cell(case, mark_criteria)),
                ]
            )
            for case in net.cases
        ]
        sections.append(dmc.Table([head, dmc.TableTbody(rows)], highlightOnHover=True))
    if net.not_covered:
        lines = [dmc.Text(f"{item.item}: {item.reason}", size="sm") for item in net.not_covered]
        sections.append(parts.panel_section(NOT_COVERED_TITLE, lines))
    return sections


def test_plan_net_section(row: SafetyNetRow | None) -> list:
    """The test plan shows the accepted net in its own read-only section (spec section 9)."""
    if row is None or not row.accepted:
        return []
    lines = [
        dmc.Text(f"{case.id}: {case.today_behaviour} ({after_mark(case)})", size="sm")
        for case in row.net.cases
    ]
    return [parts.panel_section(ACCEPTED_TITLE, lines or [dmc.Text("No tests.", size="sm")])]


def pill_text(status: str, step: str) -> str:
    """The header pill: the Phase 9 step label when it has one, otherwise the normal status."""
    return step_label(step) or status


SCOPE_GROUP_ID = "da-scope-group"
SCOPE_SAVE_ID = "da-scope-save"
SCOPE_SAVE_LABEL = "Save functions in scope"
SCOPE_TITLE = "Which functions does the change touch?"


def scope_picker(symbols: list[str], chosen: list[str]) -> list:
    """The tick list at the Understand checkpoint (D-D). Only the engine decides what is valid:
    it refuses an unknown name or an empty list. `symbols` come from the confirmed programs."""
    if not symbols:
        return []
    return [
        dmc.Box(
            [
                dmc.Text(SCOPE_TITLE, fw=600, size="sm"),
                dmc.CheckboxGroup(
                    id=SCOPE_GROUP_ID,
                    value=[name for name in chosen if name in symbols],
                    children=dmc.Stack([dmc.Checkbox(label=name, value=name) for name in symbols]),
                ),
                dmc.Button(SCOPE_SAVE_LABEL, id=SCOPE_SAVE_ID, variant="light", mt="xs"),
            ],
            p="md",
        )
    ]


def enhancement_summary(record: RequestRecord | None) -> list:
    """The Enhancement block of the Summary tab (spec section 6). Empty until a record exists."""
    if record is None or record.kind == "new":
        return []
    return [
        parts.panel_section(
            "Enhancement",
            [
                page._text_field("What it does today", record.today, False),
                page._list_field(
                    "Must NOT change",
                    [f"{item.id}: {item.text}" for item in record.must_not_change],
                    False,
                    "tabler:lock",
                    empty=NO_ENHANCEMENT,
                ),
                page._list_field(
                    "Functions in scope",
                    list(record.functions_in_scope),
                    False,
                    "tabler:code",
                    empty=NO_ENHANCEMENT,
                ),
                page._list_field(
                    "Program", list(record.targets), False, "tabler:file", empty=NO_ENHANCEMENT
                ),
            ],
        )
    ]
