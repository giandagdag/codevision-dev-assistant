"""The Admin Overview in plain code (Phase 11c, spec sections 4 and 5): one row per rulebook area,
the "Needs attention" list, and when each area last changed. No AI, nothing is written.

Like a status panel on an AS400 menu: it reads the active rulebook and a few tables, and says in
plain words what an Admin should look at. A line is `info` (amber) or `red`. An area with no line
pointing at it is green.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agents.da_admin_catalog import queue_rows
from agents.da_admin_diff import (
    AREA_BUILD,
    AREA_CATALOG,
    AREA_CHARTER,
    AREA_CODING,
    AREA_REPOSITORY,
    AREA_UI,
    TimelineRow,
    build_timeline,
)
from agents.da_admin_forms import capabilities_without_backup
from agents.da_admin_tag_cards import ai_cards
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_escalation import list_escalations
from db_table_functions.db_tbl_da_rulebook import get_active_version
from pydantic_classes.da_escalation_models import UNASSIGNED, EscalationRow
from pydantic_classes.da_rulebook_models import (
    MAX_JUDGEMENT_RULES,
    RETIRED_POLICY_FIELDS,
    Rulebook,
    RulebookVersion,
    check_charter_size,
)

# The six areas on the Overview, in tab order (tabs 2 to 7 of the console).
AREA_ORDER = (AREA_CHARTER, AREA_REPOSITORY, AREA_CATALOG, AREA_UI, AREA_CODING, AREA_BUILD)

LEVEL_INFO = "info"
LEVEL_RED = "red"
STATUS_GREEN = "green"
STATUS_AMBER = "amber"
STATUS_RED = "red"
NOTHING_TO_DO = "Nothing needs attention."
NEVER_CHANGED = "not changed since v1"
MISSING_BACKUP_FILTER = "missing_backup"


@dataclass(frozen=True)
class AttentionItem:
    area: str
    level: str  # LEVEL_INFO or LEVEL_RED
    text: str
    # Names a catalog filter the jump button should open (step 8 reads it); "" for none.
    filter: str = ""


@dataclass(frozen=True)
class AreaRow:
    area: str
    summary: str
    status: str  # green, amber or red
    last_changed: str  # "v3 by admin-0001 on 2026-11-02" or NEVER_CHANGED


@dataclass(frozen=True)
class Overview:
    version: RulebookVersion
    areas: list[AreaRow]
    attention: list[AttentionItem]


def build_overview(settings, now: datetime | None = None) -> Overview | None:
    """Everything the Overview draws, from the active version and the open Unassigned queue.
    None when no rulebook has been published yet."""
    active = get_active_version(settings.db_path)
    if active is None:
        return None
    waiting = [row.waiting_since for row in queue_rows(settings)]
    return overview_from(
        active, waiting, build_timeline(settings.db_path), now, open_escalations(settings),
        len(ai_cards()),
    )


def open_escalations(settings) -> list[EscalationRow]:
    """The open escalation rows (Phase 10), read only. Empty on a database that has none yet."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)  # makes the escalations table too
        return [row for row in list_escalations(conn) if row.outcome == "open"]


def overview_from(
    version: RulebookVersion,
    waiting_since: list[datetime | None],
    timeline: list[TimelineRow],
    now: datetime | None = None,
    escalations: list[EscalationRow] | None = None,
    ai_proposals: int = 0,
) -> Overview:
    """The pure part: given the version, the open queue's ages and the timeline, no database."""
    rulebook = version.rulebook
    items = attention_items(rulebook, waiting_since, now)
    if ai_proposals:  # fix 11-2: the AI scan's open cards
        noun = "proposal" if ai_proposals == 1 else "proposals"
        text = f"{ai_proposals} AI {noun} to review (Capability catalog tab)."
        items.append(AttentionItem(AREA_CATALOG, LEVEL_INFO, text))
    items += escalation_items(escalations or [], rulebook.policy.admin_unassigned_stale_days, now)
    summaries = area_summaries(rulebook, len(waiting_since))
    changed = last_changed(timeline)
    areas = [
        AreaRow(area, summaries[area], area_status(items, area), changed.get(area, NEVER_CHANGED))
        for area in AREA_ORDER
    ]
    return Overview(version, areas, items)


def attention_items(
    rulebook: Rulebook, waiting_since: list[datetime | None], now: datetime | None = None
) -> list[AttentionItem]:
    """The Needs attention list (spec section 4). Empty means nothing to do."""
    policy = rulebook.policy
    items: list[AttentionItem] = []
    items += _charter_items(rulebook)
    items += _rule_count_items(rulebook)
    items += _queue_items(waiting_since, policy.admin_unassigned_stale_days, now)
    items += [
        AttentionItem(
            AREA_CATALOG,
            LEVEL_INFO,
            f"Capability '{name}' has no backup senior.",
            MISSING_BACKUP_FILTER,
        )
        for name in capabilities_without_backup(policy)
    ]
    items += [
        AttentionItem(
            AREA_BUILD, LEVEL_INFO, f"{trigger.name.replace('_', ' ').capitalize()} trigger is off."
        )
        for trigger in policy.escalation_triggers
        if not trigger.on
    ]
    for label, value in (
        ("Generator model", policy.generator_model),
        ("Tester model", policy.tester_model),
        ("Program tagger model", policy.tagger_model),
    ):
        if not value.strip():
            text = f"{label}: uses the server default."
            items.append(AttentionItem(AREA_BUILD, LEVEL_INFO, text))
    items += [
        AttentionItem(
            AREA_BUILD,
            LEVEL_INFO,
            f"Retired field '{name}' is still carried; the next save drops it.",
        )
        for name in carried_retired_fields(rulebook)
    ]
    return items


def carried_retired_fields(rulebook: Rulebook) -> list[str]:
    """Retired Policy fields that this version still holds a value for (empty for a fresh seed)."""
    return [name for name in RETIRED_POLICY_FIELDS if getattr(rulebook.policy, name)]


def _charter_items(rulebook: Rulebook) -> list[AttentionItem]:
    size = check_charter_size(rulebook.charter)
    if size.status == "green":
        return []
    level = LEVEL_RED if size.status == "red" else LEVEL_INFO
    return [
        AttentionItem(
            AREA_CHARTER,
            level,
            f"Charter is at {size.percent:.0f}% of its size limit ({size.status}).",
        )
    ]


def _rule_count_items(rulebook: Rulebook) -> list[AttentionItem]:
    count = sum(1 for rule in rulebook.rules if rule.kind == "judgement")
    if count > MAX_JUDGEMENT_RULES:
        text = f"Judgement rules: {count} of {MAX_JUDGEMENT_RULES}, over the cap."
        return [AttentionItem(AREA_CODING, LEVEL_RED, text)]
    if count >= MAX_JUDGEMENT_RULES - 1:
        text = f"Judgement rules: {count} of {MAX_JUDGEMENT_RULES}."
        return [AttentionItem(AREA_CODING, LEVEL_INFO, text)]
    return []


def _queue_items(
    waiting_since: list[datetime | None], stale_days: int, now: datetime | None
) -> list[AttentionItem]:
    if not waiting_since:
        return []
    now = now or datetime.now(UTC)
    many = len(waiting_since) != 1
    items = [
        AttentionItem(
            AREA_CATALOG,
            LEVEL_INFO,
            f"{len(waiting_since)} file{'s' if many else ''} "
            f"{'wait' if many else 'waits'} for a capability (Capability catalog tab).",
        )
    ]
    limit = timedelta(days=stale_days)
    stale = sum(1 for since in waiting_since if since is not None and now - since > limit)
    if stale:
        items.append(
            AttentionItem(
                AREA_CATALOG,
                LEVEL_RED,
                f"{stale} Unassigned file{'s' if stale != 1 else ''} waiting more than "
                f"{stale_days} days.",
            )
        )
    return items


def escalation_items(
    rows: list[EscalationRow], stale_days: int, now: datetime | None = None
) -> list[AttentionItem]:
    """Phase 10 (spec section 13): open escalations with no named senior, and open ones that have
    waited longer than the same stale limit the Unassigned queue uses."""
    now = now or datetime.now(UTC)
    unnamed = sum(1 for row in rows if row.senior_label == UNASSIGNED)
    limit = timedelta(days=stale_days)
    stale = sum(1 for row in rows if row.opened_at is not None and now - row.opened_at > limit)
    items = []
    if unnamed:
        text = f"{unnamed} escalation{'s' if unnamed != 1 else ''} "
        text += "have no named senior." if unnamed != 1 else "has no named senior."
        items.append(AttentionItem(AREA_CATALOG, LEVEL_INFO, text))
    if stale:
        text = f"{stale} escalation{'s' if stale != 1 else ''} open longer than {stale_days} days."
        items.append(AttentionItem(AREA_CATALOG, LEVEL_RED, text))
    return items


def area_status(items: list[AttentionItem], area: str) -> str:
    """green: no line for this area. amber: an info line. red: a red line."""
    levels = {item.level for item in items if item.area == area}
    if LEVEL_RED in levels:
        return STATUS_RED
    return STATUS_AMBER if levels else STATUS_GREEN


def area_summaries(rulebook: Rulebook, open_unassigned: int) -> dict[str, str]:
    """One plain line per area, such as "3 capabilities, 2 Unassigned"."""
    policy = rulebook.policy
    charter = rulebook.charter
    judgement = sum(1 for rule in rulebook.rules if rule.kind == "judgement")
    ui_rules = sum(1 for rule in rulebook.rules if rule.kind == "ui_convention")
    off = [t.name for t in policy.escalation_triggers if not t.on]
    return {
        AREA_CHARTER: f"{len(charter.glossary)} glossary terms; "
        f"{check_charter_size(charter).percent:.0f}% of the size limit",
        AREA_REPOSITORY: f"{len(policy.allowed_folders)} allowed folders, "
        f"{len(policy.workspace_markers)} workspace markers",
        AREA_CATALOG: f"{len(policy.capabilities)} capabilities, {open_unassigned} Unassigned",
        AREA_UI: f"{ui_rules} UI conventions",
        AREA_CODING: f"{judgement} judgement rules (of {MAX_JUDGEMENT_RULES}), "
        f"{len(policy.approved_libraries)} approved libraries",
        AREA_BUILD: f"max {policy.build_max_rounds} fix rounds, "
        f"{len(policy.escalation_triggers) - len(off)} of {len(policy.escalation_triggers)} "
        f"triggers on, {len(policy.flag_review_zones)} zones",
    }


def server_settings_view(settings) -> list[tuple[str, str]]:
    """The read-only "Server settings" block of Repository and index (spec 11): .env name and the
    value to show. The folder is only "set" or "not set": no path, no key, no secret."""
    return [
        ("DA_SEARCH_PROVIDER", str(settings.search_provider)),
        ("DA_SEARCH_TOP_K", str(settings.search_top_k)),
        ("DA_DISCOVERY_MAX_ROUNDS", str(settings.discovery_max_rounds)),
        ("DA_MAIN_SOURCE", str(settings.main_source)),
        ("DA_SANDBOX_SOURCE_DIR", "set" if settings.sandbox_source_dir else "not set"),
        ("DA_TAGGER_MAX_MODULES", str(settings.tagger_max_modules)),
        # URL and token are only "set" / "not set": never the value
        ("DA_SONAR_URL", "set" if settings.sonar_url else "not set"),
        ("DA_SONAR_TOKEN", "set" if settings.sonar_token else "not set"),
        ("DA_SONAR_PROFILE", settings.sonar_profile or "default profile"),
        ("DA_SONAR_LANGUAGE", settings.sonar_language),
    ]


def last_changed(timeline: list[TimelineRow]) -> dict[str, str]:
    """For each area, the newest version that touched it (timeline rows are newest first)."""
    found: dict[str, str] = {}
    for row in timeline:
        for area in row.areas:
            found.setdefault(
                area, f"v{row.version_number} by {row.saved_by} on {row.saved_at:%Y-%m-%d}"
            )
    return found
