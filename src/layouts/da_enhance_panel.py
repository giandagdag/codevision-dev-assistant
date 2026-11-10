"""What the Enhance steps look like (Phase 9 step 16a): card 2 on Home, the candidate table, the
freshness banner and the enhancement summary.

Presentation only (rule R12): every text and every decision comes from the engine
(`da_enhance_flow`, `da_main_source`); nothing here searches, compares or decides. AS400 picture:
the display file for the "find the member" screen; it only says where each field goes.
"""

import dash_mantine_components as dmc

from agents.da_enhance_flow import EnhanceView
from agents.da_impact import LIMITS_LINE, summary_line
from agents.da_main_source import stale_message
from layouts import da_developer_assistant_page as page
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
        composer=page._composer("text", [], False, ""),
        panel=[*find_panel(view), *enhancement_summary(record)],
        state={"request_id": view.request_id, "revision": view.revision, "enhance": view.step},
        step=FIND_STEP,
    )


def find_panel(view: EnhanceView) -> list:
    """Candidate table, confirmed programs, and the freshness banner when there is a result."""
    sections = [parts.panel_section("Programs found", [candidate_table(view.candidates)])]
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
    body.append(dmc.Text(LIMITS_LINE, size="xs", c=da_styles.MUTED, mt=6))
    return parts.panel_section("Impact", body)


def after_mark(case: SafetyCase) -> str:
    """The "After the change" column: "Must still pass" or "Expected to change (AC-1)"."""
    if case.expected_to_change:
        return f"Expected to change ({case.expected_to_change})"
    return MUST_STILL_PASS


def safety_net_tab(row: SafetyNetRow | None) -> list:
    """The Safety net tab (spec section 8, step 6): banner, table, and the not-covered card."""
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
                    dmc.TableTd(after_mark(case)),
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
