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

from db_table_functions.db_tbl_da_rulebook import (
    RulebookError,
    StaleSaveError,
    get_version,
    save_new_version,
)
from pydantic_classes.da_rulebook_models import Charter, Policy, Rulebook

TAB_CHARTER = "charter"
TAB_BUILD = "build"

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


def rulebook_from_form(base: Rulebook, tab: str, form: dict) -> Rulebook:
    """The rulebook with this tab's form values applied. Raises ValidationError on bad values."""
    if tab == TAB_CHARTER:
        return base.model_copy(update={"charter": _charter_from_form(base.charter, form)})
    if tab == TAB_BUILD:
        return base.model_copy(update={"policy": _policy_from_build_form(base.policy, form)})
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
    try:
        saved = save_new_version(db_path, edited, base_version, user_id, note)
    except StaleSaveError as error:
        return SaveResult(RESULT_STALE, message=str(error), newest_version=_newest(error))
    except RulebookError as error:
        return _result_from_refusal(str(error))
    return SaveResult(
        RESULT_SAVED, version_number=saved.version_number, warnings=_warnings(edited)
    )


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

