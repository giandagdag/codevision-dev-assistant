"""What the Enhance steps look like (Phase 9 step 16a): card 2 on Home, the candidate table, the
freshness banner and the enhancement summary.

Presentation only (rule R12): every text and every decision comes from the engine
(`da_enhance_flow`, `da_main_source`); nothing here searches, compares or decides. AS400 picture:
the display file for the "find the member" screen; it only says where each field goes.
"""

import dash_mantine_components as dmc

from agents.da_enhance_flow import EnhanceView
from agents.da_main_source import stale_message
from layouts import da_developer_assistant_page as page
from pydantic_classes.da_enhance_models import Candidate
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
