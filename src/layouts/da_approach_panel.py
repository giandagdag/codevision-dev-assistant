"""The Approach tab (spec section 9): file plan, reuse, design decisions, libraries and zones,
test plan and the four gate checks.

Presentation only (rule R12), like the other layout files: it turns data the Approach flow
already prepared into components. Nothing here decides a status or a check. All text from the
AI or the developer goes in as plain strings, never as HTML (rule R11).
"""

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from pydantic_classes.da_approach_models import (
    ApproachVersion,
    ApproachView,
    TestCase,
)
from pydantic_classes.da_discovery_models import DiscoveryResult
from pydantic_classes.da_models import STATUS_READY_TO_BUILD
from pydantic_classes.da_workspace_models import CheckResult
from styles import da_styles

DRAFT_BANNER = "Draft: may change after your choices"
TESTS_LINE = "written by the Tester, frozen, in Phase 6"
READY_LINE = "READY TO BUILD"
NEGATIVE_LABEL = "Negative scenario"
# The same look as the criteria in the Summary tab: a badge's text is never cut with '...'.
ID_BADGE_STYLE = {"flexShrink": 0, "overflow": "visible", "width": "auto"}
ID_BADGE_STYLES = {"label": {"overflow": "visible", "textOverflow": "clip"}}
ACTION_LABELS = {"create": "New", "modify": "Change"}


FOUND_IN_WORKSPACE = "Checked: found in your workspace"


def workspace_note(path: str, check: CheckResult | None) -> str:
    """What the workspace check says about a file the plan changes (spec section 9), or "" if no
    check has run (or the folder itself was wrong, so nothing can be said about a file)."""
    if check is None or any(item.code in ("B1", "B2") for item in check.blockers):
        return ""
    for blocker in check.blockers:
        if blocker.code == "B3" and blocker.path == path:
            return blocker.text
    return FOUND_IN_WORKSPACE


def approach_panel(view: ApproachView, check: CheckResult | None = None) -> list:
    """The whole tab, top to bottom. `check` is the latest workspace check, if there is one."""
    approach = view.approach
    if approach is None:
        return [dmc.Text("No approach yet.", style=da_styles.EMPTY_TEXT)]
    parts: list = [_header(view, approach)]
    if view.step == "choices":
        parts.append(
            dmc.Alert(DRAFT_BANNER, color="orange", variant="light", id="da-approach-draft")
        )
    parts += [
        _section("File plan", _file_plan(view, approach, check), "da-file-plan"),
        _section("Reuse decisions", _reuse_table(view.discovery, approach), "da-reuse"),
        _section("Design decisions", _decisions(approach), "da-design-decisions"),
        _section("Libraries and zones", _libraries_and_warnings(approach, check), "da-libraries"),
    ]
    if view.plan is not None:
        parts.append(_section("Test plan", _test_plan(view), "da-test-plan"))
    parts.append(_section("Gate", _gate(view), "da-gate"))
    return parts


def _header(view: ApproachView, approach: ApproachVersion) -> dmc.Text:
    return dmc.Text(
        f"Approach v{approach.approach_version}, built from request v{approach.record_version} "
        f"and Discovery round {approach.discovery_round}",
        size="xs",
        c=da_styles.MUTED,
        id="da-approach-header",
    )


def _section(title: str, body, section_id: str) -> dmc.Box:
    return dmc.Box(
        [dmc.Text(title, fw=700, size="sm", c=da_styles.NAVY, mb=6), body],
        style=da_styles.PANEL_SECTION,
        id=section_id,
    )


# --- file plan ---


def _file_plan(view: ApproachView, approach: ApproachVersion, check: CheckResult | None = None):
    plan = approach.plan
    hit_names = {hit.hit_id: hit.symbol or hit.source_path for hit in _hits(view.discovery)}
    rows = []
    for item in plan.files:
        notes = []
        if item.reuses:
            notes.append("Reuses " + ", ".join(hit_names.get(n, f"hit {n}") for n in item.reuses))
        if any(w.startswith(f"{item.path}: Not found in Discover") for w in approach.warnings):
            notes.append(workspace_note(item.path, check) or "Not found in Discover")
        rows.append(
            dmc.TableTr(
                [
                    dmc.TableTd(dmc.Text(item.path, size="xs", ff="monospace")),
                    dmc.TableTd(
                        dmc.Badge(
                            ACTION_LABELS[item.action],
                            size="sm",
                            variant="light",
                            color="blue" if item.action == "create" else "gray",
                            style=ID_BADGE_STYLE,
                            styles=ID_BADGE_STYLES,
                        )
                    ),
                    dmc.TableTd(dmc.Text(item.purpose, size="xs")),
                    dmc.TableTd(dmc.Text("; ".join(notes), size="xs", c=da_styles.MUTED)),
                ]
            )
        )
    rows.append(
        dmc.TableTr(
            [
                dmc.TableTd(dmc.Text(view.tests_folder, size="xs", ff="monospace")),
                dmc.TableTd(
                    dmc.Badge(
                        "Tests",
                        size="sm",
                        variant="light",
                        color="violet",
                        style=ID_BADGE_STYLE,
                        styles=ID_BADGE_STYLES,
                    )
                ),
                dmc.TableTd(dmc.Text(TESTS_LINE, size="xs")),
                dmc.TableTd(""),
            ]
        )
    )
    head = dmc.TableThead(
        dmc.TableTr(
            [dmc.TableTh("File"), dmc.TableTh("Action"), dmc.TableTh("Why"), dmc.TableTh("Note")]
        )
    )
    count = len(plan.files)
    noun = "code file" if count == 1 else "code files"
    return dmc.Box(
        [
            dmc.Text(plan.summary, size="sm", mb=6),
            dmc.Table([head, dmc.TableTbody(rows)]),
            dmc.Text(
                f"{count} {noun}, limit {view.file_limit}",
                size="xs",
                c="red" if count > view.file_limit else da_styles.MUTED,
                id="da-file-footer",
            ),
        ]
    )


def _hits(discovery: DiscoveryResult | None):
    return discovery.hits if discovery else []


# --- reuse decisions ---


def _reuse_table(discovery: DiscoveryResult | None, approach: ApproachVersion):
    decisions = approach.plan.reuse_decisions
    if not decisions:
        return dmc.Text("Nothing to reuse was decided.", style=da_styles.EMPTY_TEXT)
    hits = {hit.hit_id: hit for hit in _hits(discovery)}
    titles = {}
    for finding in discovery.findings if discovery else []:
        for hit_id in finding.hit_ids:
            titles.setdefault(hit_id, finding.title)
    rows = []
    for item in decisions:
        hit = hits.get(item.hit_id)
        where = f"{hit.source_path} · {hit.symbol}" if hit and hit.symbol else (
            hit.source_path if hit else f"hit {item.hit_id}"
        )
        rows.append(
            dmc.TableTr(
                [
                    dmc.TableTd(
                        [
                            dmc.Text(titles.get(item.hit_id, "Found by Discover"), size="xs"),
                            dmc.Text(where, size="xs", c=da_styles.MUTED, ff="monospace"),
                        ]
                    ),
                    dmc.TableTd(
                        dmc.Badge(
                            item.decision,
                            size="sm",
                            variant="light",
                            color="gray" if item.decision == "ignore" else "green",
                            style=ID_BADGE_STYLE,
                            styles=ID_BADGE_STYLES,
                        )
                    ),
                    dmc.TableTd(dmc.Text(item.reason, size="xs")),
                ]
            )
        )
    head = dmc.TableThead(
        dmc.TableTr([dmc.TableTh("Found"), dmc.TableTh("Decision"), dmc.TableTh("Why")])
    )
    return dmc.Table([head, dmc.TableTbody(rows)])


# --- design decisions ---


def _decisions(approach: ApproachVersion):
    if not approach.decisions:
        text = "Design choices appear here once you answer them."
        if not approach.plan.design_choices:
            text = "No design choices were needed."
        return dmc.Text(text, style=da_styles.EMPTY_TEXT)
    lines = []
    for item in approach.decisions:
        lines.append(
            dmc.Group(
                [
                    DashIconify(icon="tabler:check", width=16, color=da_styles.MUTED),
                    dmc.Text(f"{item.question} {item.choice}", size="sm"),
                    dmc.Badge("Your own answer", size="xs", variant="light", color="gray")
                    if item.custom
                    else None,
                ],
                gap=6,
                wrap="nowrap",
            )
        )
    return dmc.Box(lines)


# --- libraries, zones and warnings ---


def _libraries_and_warnings(approach: ApproachVersion, check: CheckResult | None = None):
    chips = [
        dmc.Badge(name, variant="light", color="blue", tt="none")
        for name in approach.plan.libraries
    ] or [dmc.Text("No libraries beyond the standard library.", style=da_styles.EMPTY_TEXT)]
    lines = [
        dmc.Group(
            [
                DashIconify(icon="tabler:alert-triangle", width=16, color=da_styles.MUTED),
                dmc.Text(_warning_text(warning, approach, check), size="sm"),
            ],
            gap=6,
            wrap="nowrap",
            align="flex-start",
        )
        for warning in approach.warnings
    ] or [dmc.Text("No warnings.", style=da_styles.EMPTY_TEXT)]
    return dmc.Box([dmc.Group(chips, gap=6, mb=8), *lines])


def _warning_text(warning: str, approach: ApproachVersion, check: CheckResult | None) -> str:
    """The "Not found in Discover" warning, once the workspace check has settled it."""
    for item in approach.plan.files:
        if warning.startswith(f"{item.path}: Not found in Discover"):
            note = workspace_note(item.path, check)
            return f"{item.path}: {note}" if note else warning
    return warning


# --- test plan ---


def _ac_badge(criterion_id: str, negative: bool):
    """The criterion ID badge, with the asterisk of a negative scenario after it (as in 2D)."""
    mark = (
        dmc.Tooltip(
            dmc.Text("*", size="sm", fw=700, **{"aria-label": NEGATIVE_LABEL}),
            label=NEGATIVE_LABEL,
        )
        if negative
        else None
    )
    return dmc.Group(
        [
            dmc.Badge(
                criterion_id,
                size="sm",
                variant="light",
                color="blue",
                style=ID_BADGE_STYLE,
                styles=ID_BADGE_STYLES,
            ),
            mark,
        ],
        gap=2,
        wrap="nowrap",
    )


def _case_row(case: TestCase, negatives: set[str], draft: bool = False) -> dmc.TableTr:
    tag = dmc.Badge("Yours", size="xs", color="violet", variant="light") if (
        case.source == "developer"
    ) else None
    if draft:
        tag = dmc.Badge("Draft", size="xs", color="orange", variant="light")
    # Dash refuses id=None, so the highlight props are only passed for the draft row.
    extra = {"style": {"background": da_styles.HIGHLIGHT}, "id": "da-draft-case"} if draft else {}
    return dmc.TableTr(
        [
            dmc.TableTd(dmc.Group([dmc.Text(case.test_id, size="xs", ff="monospace"), tag], gap=4)),
            dmc.TableTd(_ac_badge(case.criterion_id, case.criterion_id in negatives)),
            dmc.TableTd(dmc.Text(case.given, size="xs")),
            dmc.TableTd(dmc.Text(case.expect, size="xs")),
        ],
        **extra,
    )


def _test_plan(view: ApproachView):
    plan = view.plan
    negatives = {c.id for c in view.record.acceptance_criteria if c.kind == "failure"}
    rows = [_case_row(case, negatives) for case in plan.cases]
    if view.draft_case is not None:
        draft = view.draft_case
        # The number it gets if it is kept (the highest number in the plan, plus one).
        next_number = max((int(case.test_id.split("-")[1]) for case in plan.cases), default=0) + 1
        rows.append(
            _case_row(
                TestCase(
                    test_id=f"T-{next_number}", criterion_id=draft.criterion_id, given=draft.given,
                    expect=draft.expect, source="developer",
                ),
                negatives,
                draft=True,
            )
        )
    head = dmc.TableThead(
        dmc.TableTr(
            [dmc.TableTh("Test"), dmc.TableTh("Criterion"), dmc.TableTh("Given"),
             dmc.TableTh("Expect")]
        )
    )
    total = len(view.record.acceptance_criteria)
    covered = len({case.criterion_id for case in plan.cases})
    legend = dmc.Text(
        f"* {NEGATIVE_LABEL} testing", size="xs", c=da_styles.MUTED, id="da-tests-legend"
    )
    return dmc.Box(
        [
            dmc.Table([head, dmc.TableTbody(rows)]),
            dmc.Text(
                f"{len(plan.cases)} cases cover {covered} of {total} criteria",
                size="xs",
                c=da_styles.MUTED,
                id="da-test-cover",
            ),
            legend,
        ]
    )


# --- the gate ---


def _gate(view: ApproachView):
    lines = []
    for number, check in enumerate(view.gate, start=1):
        icon = "tabler:circle-check" if check.passed else "tabler:circle"
        lines.append(
            dmc.Group(
                [
                    DashIconify(
                        icon=icon, width=18, color=da_styles.BLUE if check.passed else "#A8AFBC"
                    ),
                    dmc.Text(f"{number}. {check.name}", size="sm", fw=600),
                    dmc.Text(check.detail, size="xs", c=da_styles.MUTED),
                ],
                gap=8,
                wrap="nowrap",
                id=f"da-gate-{number}",
            )
        )
    if view.request.status == STATUS_READY_TO_BUILD:
        lines.append(
            dmc.Alert(READY_LINE, color="green", variant="light", id="da-ready-banner")
        )
    return dmc.Box(lines)
