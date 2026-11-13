"""Turn an Admin form into a new rulebook version (spec sections 3 and 8, decision D-C).

Plain code, no AI. Each tab has one function that builds the edited rulebook from the form values,
and one shared save function that maps every Phase 1 refusal to a plain result the screen can show.
Nothing is written until save_from_form runs, so Cancel is simply "do not call it".

Form values come from the screen as text, so numbers may arrive as "9". Pydantic turns them into
numbers, and a value that does not fit is reported as "field: message" (11-19).
"""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from agents.da_approach_checks import library_name
from db_table_functions.db_tbl_da_rulebook import (
    RulebookError,
    StaleSaveError,
    get_version,
    next_rule_id,
    save_new_version,
)
from pydantic_classes.da_rulebook_models import (
    MAX_JUDGEMENT_RULES,
    Charter,
    GoldenExample,
    Policy,
    Rule,
    Rulebook,
    find_rulebook_problems,
)

TAB_CHARTER = "charter"
TAB_BUILD = "build"
TAB_UI = "ui"
TAB_CODING = "coding"
TAB_CAPABILITY = "capability"
# The rule table each rule tab edits (the kind is fixed by the tab).
KIND_OF_TAB = {TAB_UI: "ui_convention", TAB_CODING: "judgement"}
_RULE_TEXT_FIELDS = ("title", "why", "good_example", "bad_example", "source")

RESULT_SAVED = "saved"
RESULT_PROBLEMS = "problems"
RESULT_STALE = "stale"
RESULT_UNCHANGED = "unchanged"
RESULT_REFUSED_NOTE = "refused_note"

# Shown on the Build and test tab as plain fields, in this order.
CORE_BUILD_FIELDS: tuple[str, ...] = ("build_max_rounds", "build_test_timeout_seconds", "max_files")
# Collapsed under "Advanced limits": every other number on the policy (spec section 8).
ADVANCED_LIMIT_FIELDS: tuple[str, ...] = (
    "build_max_prompt_chars",
    "build_max_parallel",
    "tester_max_prompt_chars",
    "tester_max_attempts",
    "tester_quote_window",
    "refine_max_per_request",
    "refine_lane_max_attempts",
    "refine_repro_max_attempts",
    "refine_conflict_context_lines",
    "enhance_name_top_k",
    "enhance_meaning_top_k",
    "enhance_find_max_rounds",
    "enhance_max_keep_items",
    "safety_net_max_tests",
    "safety_net_max_attempts",
    "safety_net_max_corrections",
    "impact_max_callers",
    "max_design_choices",
    "max_material_decisions",
    "admin_unassigned_stale_days",
)
_MODEL_FIELDS = ("generator_model", "tester_model")
_CHARTER_TEXT_LISTS = ("in_scope", "out_of_scope", "architecture_principles", "constraints")


@dataclass(frozen=True)
class SaveResult:
    """What happened on Save. kind is one of the RESULT_ words."""

    kind: str
    message: str = ""
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    version_number: int | None = None
    newest_version: int | None = None


def field_bounds(field_name: str) -> str:
    """A short hint such as "1 to 5", read from the model so the screen repeats no numbers."""
    info = Policy.model_fields[field_name]
    low = high = None
    for item in info.metadata:
        low = getattr(item, "ge", low)
        high = getattr(item, "le", high)
    if low is not None and high is not None:
        return f"{low} to {high}"
    if low is not None:
        return f"{low} or more"
    return ""


class FormError(ValueError):
    """A form value that cannot become a rulebook part. Carries every problem in plain words."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def rulebook_from_form(base: Rulebook, tab: str, form: dict) -> Rulebook:
    """The rulebook with this tab's form values applied.

    Raises ValidationError or FormError on bad values."""
    if tab == TAB_CHARTER:
        return base.model_copy(update={"charter": _charter_from_form(base.charter, form)})
    if tab == TAB_BUILD:
        return base.model_copy(update={"policy": _policy_from_build_form(base.policy, form)})
    if tab == TAB_UI:
        rules = _rules_from_form(base.rules, "ui_convention", form)
        return base.model_copy(update={"rules": rules})
    if tab == TAB_CODING:
        return _coding_from_form(base, form)
    if tab == TAB_CAPABILITY:
        return base.model_copy(update={"policy": _policy_from_catalog_form(base.policy, form)})
    raise ValueError(f"Unknown tab '{tab}'.")


def save_from_form(
    db_path: Path, tab: str, form: dict, base_version: int, user_id: str, note: str
) -> SaveResult:
    """Validate the form and save it as the next version. Never raises for an Admin mistake."""
    base = get_version(db_path, base_version)
    if base is None:
        return SaveResult(RESULT_PROBLEMS, problems=[f"Version v{base_version} does not exist."])
    try:
        edited = rulebook_from_form(base.rulebook, tab, form)
    except ValidationError as error:
        return SaveResult(RESULT_PROBLEMS, problems=_plain_errors(error))
    except FormError as error:
        return SaveResult(RESULT_PROBLEMS, problems=error.problems)
    tab_problems = _tab_problems(tab, edited)
    if tab_problems:
        # The whole list at once: this tab's checks plus the Phase 1 checks (spec 11-14).
        return SaveResult(
            RESULT_PROBLEMS, problems=[*tab_problems, *find_rulebook_problems(edited)]
        )
    try:
        saved = save_new_version(db_path, edited, base_version, user_id, note)
    except StaleSaveError as error:
        return SaveResult(RESULT_STALE, message=str(error), newest_version=_newest(error))
    except RulebookError as error:
        return _result_from_refusal(str(error))
    warnings = _warnings(edited)
    if tab == TAB_CAPABILITY:
        warnings += pattern_warnings(edited.policy)
    return SaveResult(RESULT_SAVED, version_number=saved.version_number, warnings=warnings)


# --- Charter ---


def _charter_from_form(current: Charter, form: dict) -> Charter:
    data = current.model_dump()
    if "purpose" in form:
        data["purpose"] = str(form["purpose"]).strip()
    for name in _CHARTER_TEXT_LISTS:
        if name in form:
            data[name] = _clean_list(form[name])
    if "glossary" in form:
        data["glossary"] = _glossary_rows(form["glossary"])
    return Charter.model_validate(data)


def _glossary_rows(rows: list[dict]) -> list[dict]:
    # A completely empty row (Add row, nothing typed) is dropped; a half-filled one is an error.
    cleaned = [
        {"term": str(row.get("term", "")).strip(), "meaning": str(row.get("meaning", "")).strip()}
        for row in rows
    ]
    return [row for row in cleaned if row["term"] or row["meaning"]]


# --- Build and test ---


def _policy_from_build_form(current: Policy, form: dict) -> Policy:
    data = current.model_dump()
    for name in (*CORE_BUILD_FIELDS, *ADVANCED_LIMIT_FIELDS):
        if name in form:
            data[name] = _number(form[name])
    for name in _MODEL_FIELDS:
        if name in form:
            data[name] = str(form[name] or "").strip()
    if "triggers" in form:
        data["escalation_triggers"] = _trigger_rows(form["triggers"])
    if "zones" in form:
        data["flag_review_zones"] = _zone_rows(form["zones"])
    if "protected_files" in form:
        data["protected_files"] = _clean_list(form["protected_files"])
    return Policy.model_validate(data)


def _number(value):
    # Keep text as text: pydantic reports "abc" as a plain error, and turns "9" into 9.
    return value.strip() if isinstance(value, str) else value


def _trigger_rows(triggers) -> list[dict]:
    """Accept {"name": True} or a list of {"name":..., "on":...}. The form offers five switches."""
    if isinstance(triggers, dict):
        return [{"name": name, "on": bool(on)} for name, on in triggers.items()]
    return [{"name": row["name"], "on": bool(row["on"])} for row in triggers]


def _zone_rows(rows: list[dict]) -> list[dict]:
    zones = []
    for row in rows:
        zone = {
            "name": str(row.get("name", "")).strip(),
            "description": str(row.get("description", "")).strip(),
            "examples": _clean_list(row.get("examples", [])),
            "path_patterns": _clean_list(row.get("path_patterns", [])),
        }
        if zone["name"] or zone["description"] or zone["examples"] or zone["path_patterns"]:
            zones.append(zone)
    return zones


def _clean_list(value) -> list[str]:
    """A list of words from a list, or from text with one item per line. Blank items are dropped."""
    items = value.splitlines() if isinstance(value, str) else value
    return [text for text in (str(item).strip() for item in items) if text]


# --- UI standards and Coding standards (Phase 11b) ---


@dataclass(frozen=True)
class AddRowResult:
    """What the Add row button on a rule table got: a new rule ID, or a message and no row."""

    rule_id: str = ""
    message: str = ""


def add_rule_row(db_path: Path, kind: str, rows_now: int) -> AddRowResult:
    """Hand out the next rule ID for a new row (spec 11-12), unless the judgement cap is reached.

    The number is used up at once, even if Cancel follows (Phase 1 rule R7). rows_now is how many
    rules of this kind the draft form holds, so the cap counts unsaved rows too (11-13)."""
    if kind == "judgement" and rows_now >= MAX_JUDGEMENT_RULES:
        return AddRowResult(
            message=f"There are already {MAX_JUDGEMENT_RULES} judgement rules, the most the pilot "
            "allows. Remove one before adding another."
        )
    return AddRowResult(rule_id=next_rule_id(db_path, kind))


def rule_counter_text(kind: str, count: int) -> str:
    """"7 of 10" for judgement rules; a plain count for UI rules, which have no cap."""
    if kind == "judgement":
        return f"{count} of {MAX_JUDGEMENT_RULES}"
    return str(count)


def _rules_from_form(current: list[Rule], kind: str, form: dict) -> list[Rule]:
    """Replace the rules of this kind with the form rows. Rules of the other kind stay as they are.

    A row that holds only its ID (Add row, nothing typed) is dropped; its ID stays used up."""
    if "rules" not in form:
        return list(current)
    rows, problems = [], []
    for row in form["rules"]:
        rule_id = str(row.get("rule_id", "")).strip()
        typed = {name: str(row.get(name, "")).strip() for name in _RULE_TEXT_FIELDS}
        tags = _clean_list(row.get("tags", []))
        severity = str(row.get("severity", "")).strip()
        if not any(typed.values()) and not tags:
            continue  # nothing typed: an untouched new row (or a blank one) is dropped
        if not rule_id:
            problems.append("A rule row has no rule ID. Use Add row to get one.")
            continue
        try:
            rows.append(
                Rule.model_validate(
                    {"rule_id": rule_id, "kind": kind, "tags": tags, "severity": severity, **typed}
                )
            )
        except ValidationError as error:
            problems.extend(f"{rule_id} {line}" for line in _plain_errors(error))
    if problems:
        raise FormError(problems)
    return _merge_rules(current, kind, rows)


def _merge_rules(current: list[Rule], kind: str, rows: list[Rule]) -> list[Rule]:
    # Keep each rule's place so an unchanged form gives an identical rulebook ("No changes").
    queue = iter(rows)
    merged = []
    for rule in current:
        if rule.kind != kind:
            merged.append(rule)
        elif (replacement := next(queue, None)) is not None:
            merged.append(replacement)
    merged.extend(queue)
    return merged


def _coding_from_form(base: Rulebook, form: dict) -> Rulebook:
    data = base.policy.model_dump()
    if "approved_libraries" in form:
        data["approved_libraries"] = _clean_list(form["approved_libraries"])
    if "blocked_imports" in form:
        data["build_blocked_imports"] = _clean_list(form["blocked_imports"])
    if "sonar_map" in form:
        data["sonar_severity_map"] = {
            str(key).strip(): str(value).strip() for key, value in form["sonar_map"].items()
        }
    update = {
        "rules": _rules_from_form(base.rules, "judgement", form),
        "policy": Policy.model_validate(data),
    }
    if "golden_examples" in form:
        update["golden_examples"] = [
            GoldenExample.model_validate(row) for row in _golden_rows(form["golden_examples"])
        ]
    return base.model_copy(update=update)


def _golden_rows(rows: list[dict]) -> list[dict]:
    cleaned = [
        {
            "title": str(row.get("title", "")).strip(),
            "tags": _clean_list(row.get("tags", [])),
            "code": str(row.get("code", "")).strip(),
            "why": str(row.get("why", "")).strip(),
        }
        for row in rows
    ]
    return [row for row in cleaned if row["title"] or row["code"] or row["tags"] or row["why"]]


def library_overlap_problems(policy: Policy) -> list[str]:
    """A library on both the approved list and the blocked list (spec 11-14). "Blocked wins" in
    Build, so the Admin must decide which list it belongs on. Compared the way Approach compares
    names: lower case, "-" and "_" alike."""
    blocked = {library_name(name) for name in policy.build_blocked_imports}
    return [
        f"Library '{name}' is on both the approved list and the blocked list. "
        "Take it off one of them."
        for name in policy.approved_libraries
        if library_name(name) in blocked
    ]


def _tab_problems(tab: str, rulebook: Rulebook) -> list[str]:
    """Checks that belong to one tab only, so they can never lock a save on another tab."""
    if tab != TAB_CODING:
        return []
    titles: set[str] = set()
    problems = library_overlap_problems(rulebook.policy)
    for example in rulebook.golden_examples:
        key = example.title.strip().lower()
        if key in titles:
            problems.append(f"Golden example '{example.title}' is listed more than once.")
        titles.add(key)
    return problems


# --- Capability catalog (Phase 11b) ---

_PATTERN_MARKS = "*?["


def capability_rows(policy: Policy) -> list[dict]:
    """The catalog as form rows (patterns as one-per-line text), in catalog order."""
    return [
        {
            "name": c.name,
            "description": c.description,
            "named_senior": c.named_senior,
            "backup_senior": c.backup_senior,
            "path_patterns": "\n".join(c.path_patterns),
        }
        for c in policy.capabilities
    ]


def move_row(rows: list, index: int, step: int) -> list:
    """A copy of the rows with row `index` moved up (step -1) or down (step +1). First match wins
    in the catalog, so order matters. At either end nothing moves."""
    target = index + step
    if not (0 <= index < len(rows) and 0 <= target < len(rows)):
        return list(rows)
    moved = list(rows)
    moved[index], moved[target] = moved[target], moved[index]
    return moved


def capabilities_without_backup(policy: Policy) -> list[str]:
    """Names of capabilities with no backup senior. Phase 11c shows this on the Overview."""
    return [c.name for c in policy.capabilities if not c.backup_senior.strip()]


def _policy_from_catalog_form(current: Policy, form: dict) -> Policy:
    data = current.model_dump()
    if "capabilities" in form:
        data["capabilities"] = _capability_form_rows(form["capabilities"])
    return Policy.model_validate(data)


def _capability_form_rows(rows: list[dict]) -> list[dict]:
    cleaned = [
        {
            "name": str(row.get("name", "")).strip(),
            "description": str(row.get("description", "")).strip(),
            "named_senior": str(row.get("named_senior", "")).strip(),
            "backup_senior": str(row.get("backup_senior", "")).strip(),
            "path_patterns": _clean_list(row.get("path_patterns", [])),
        }
        for row in rows
    ]
    # A completely empty row (Add row, nothing typed) is dropped; a half-filled one is an error.
    return [row for row in cleaned if any(row.values())]


def pattern_warnings(policy: Policy) -> list[str]:
    """A path pattern that cannot match any allowed folder (a warning, not a refusal).

    A pattern starting with * or ? may match any root and never warns. Otherwise the text before
    the first wildcard must start inside an allowed folder, or be the start of one's path."""
    folders = [f.strip("/").lower() for f in policy.allowed_folders]
    warnings = []
    for capability in policy.capabilities:
        for pattern in capability.path_patterns:
            if not _can_match_a_folder(pattern, folders):
                warnings.append(
                    f"Capability '{capability.name}': pattern '{pattern}' cannot match any "
                    "allowed folder."
                )
    return warnings


def _can_match_a_folder(pattern: str, folders: list[str]) -> bool:
    text = pattern.strip().lower()
    if not text or text[0] in "*?":
        return True
    cut = next((i for i, ch in enumerate(text) if ch in _PATTERN_MARKS), len(text))
    start = text[:cut]
    return any(
        start == folder or start.startswith(folder + "/") or folder.startswith(start)
        for folder in folders
    )


# --- Results ---


def _plain_errors(error: ValidationError) -> list[str]:
    lines = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"] if not isinstance(part, int))
        bound = ""
        if item["loc"] and item["loc"][0] in Policy.model_fields and field_bounds(item["loc"][0]):
            bound = f" (allowed: {field_bounds(item['loc'][0])})"
        lines.append(f"{where}: {item['msg']}{bound}")
    return lines


def _newest(error: StaleSaveError) -> int | None:
    # The Phase 1 message reads "... but v4 is now the active version ...".
    text = str(error)
    marker = "but v"
    if marker not in text:
        return None
    digits = text.split(marker, 1)[1].split(" ", 1)[0]
    return int(digits) if digits.isdigit() else None


def _result_from_refusal(message: str) -> SaveResult:
    if message.startswith("The change note is empty"):
        return SaveResult(RESULT_REFUSED_NOTE, message=message)
    if message.startswith("No changes to save"):
        return SaveResult(RESULT_UNCHANGED, message=message)
    lines = [line[2:] for line in message.splitlines() if line.startswith("- ")]
    return SaveResult(RESULT_PROBLEMS, message=message, problems=lines or [message])


def _warnings(rulebook: Rulebook) -> list[str]:
    # A protected pattern that is also a whole allowed folder would lock the folder (spec 8).
    folders = {folder.strip("/") for folder in rulebook.policy.allowed_folders}
    return [
        f"Protected pattern '{pattern}' is also a whole folder in the allowed folders."
        for pattern in rulebook.policy.protected_files
        if pattern.strip("/") in folders
    ]

