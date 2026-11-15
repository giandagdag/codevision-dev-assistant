"""Data shapes for the rulebook, and the checks a rulebook must pass before it is saved.

Pydantic checks the shape (field types and allowed words). find_rulebook_problems checks the
house rules from spec rule R3 and returns every problem as a plain sentence, so an Admin sees
the whole list at once instead of fixing one error per attempt.
"""

import re
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
)

RuleKind = Literal["judgement", "ui_convention"]
Severity = Literal["must_fix", "should_fix", "fyi"]
Level = Literal["L0", "L1", "L2", "L3"]
CharterStatus = Literal["green", "amber", "red"]

RULE_ID_PREFIXES: dict[str, str] = {"judgement": "CV-PY", "ui_convention": "CV-UI"}
# Three or more digits, so rule 1000 still fits.
RULE_ID_PATTERN = r"^CV-(PY|UI)-\d{3,}$"

MAX_JUDGEMENT_RULES = 10

# The five fixed escalation triggers (redesign 5.11). Phase 10 acts on them; Admin only turns them
# on or off.
ESCALATION_TRIGGER_NAMES: tuple[str, ...] = (
    "cap_hit_twice",
    "out_of_scope",
    "dispute",
    "tester_unable_twice",
    "get_help",
)
# Names used before Phase 11 and the new name each one becomes when an old version is loaded.
OLD_TRIGGER_NAMES: dict[str, str] = {
    "max_rounds_with_must_fix_open": "cap_hit_twice",
    "developer_disputes_finding": "dispute",
}
# Fields the redesign removed. Old saved versions still hold them, so they stay on the model as
# optional; saves leave them out.
RETIRED_POLICY_FIELDS: tuple[str, ...] = (
    "default_level",
    "max_level",
    "never_generate_zones",
    "max_review_rounds",
)

CHARTER_CHARACTER_LIMIT = 6000
CHARTER_AMBER_PERCENT = 80


class _RulebookPart(BaseModel):
    # extra="forbid": a misspelt field name in the seed file is an error, not silently dropped.
    model_config = ConfigDict(extra="forbid")


class GlossaryEntry(_RulebookPart):
    term: str = Field(min_length=1)
    meaning: str = Field(min_length=1)


class Charter(_RulebookPart):
    purpose: str = Field(min_length=1)
    in_scope: list[str]
    out_of_scope: list[str]
    architecture_principles: list[str]
    constraints: list[str]
    glossary: list[GlossaryEntry]


class Rule(_RulebookPart):
    rule_id: str = Field(pattern=RULE_ID_PATTERN)
    title: str = Field(min_length=1)
    kind: RuleKind
    tags: list[str] = Field(min_length=1)
    severity: Severity
    why: str = Field(min_length=1)
    good_example: str = Field(min_length=1)
    bad_example: str = Field(min_length=1)
    source: str = Field(min_length=1)


class NeverGenerateZone(_RulebookPart):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    examples: list[str]


class FlagReviewZone(_RulebookPart):
    """An area where touching a file makes a named senior a required reviewer (Phase 4, D-E).
    Like dual control: it never blocks, it only adds a second signature."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    examples: list[str] = Field(default_factory=list)
    # Matched by plain code against the whole lower-case path (fnmatch), never by the AI.
    path_patterns: list[str] = Field(min_length=1)


class Capability(_RulebookPart):
    """A business area in the catalog (Phase 9, D-B): files that match its patterns belong to it,
    and the named senior signs off changes there. Like an application owner list on the AS400."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    # A role or person label, text only (made up here; the real list is work fact WF-2).
    named_senior: str = Field(min_length=1)
    # Phase 11b: who signs off when the named senior is away. Empty for versions saved before.
    backup_senior: str = ""
    # Matched by plain code against the whole lower-case path (fnmatch), never by the AI.
    path_patterns: list[str] = Field(min_length=1)


class GoldenExample(_RulebookPart):
    """A model piece of code Admin keeps as a good example. Stored only in Phase 11: it is not
    sent to any AI call yet (decision D-H)."""

    title: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    code: str = Field(min_length=1)
    why: str = ""


# Starter values for the Phase 4 policy fields (made up; the real values are set at work). A
# rulebook version saved before Phase 4 has none of them, so each field defaults to these.
DEFAULT_ALLOWED_FOLDERS = [
    "src/configs",
    "src/agents",
    "src/pydantic_classes",
    "src/db_table_functions",
    "src/callbacks",
    "src/layouts",
    "src/styles",
    "src/web",
]
DEFAULT_NEW_FILE_NAME_PATTERN = r"^[a-z][a-z0-9_]*\.py$"
DEFAULT_PROTECTED_FILES = [
    ".env",
    "*/.env*",
    "src/configs/llm_config.py",
    "src/web/web_server.py",
    "src/callbacks/universal_callbacks.py",
]
# "requests" is not listed: Build blocks it and "blocked wins", so listing it here only disagreed.
DEFAULT_APPROVED_LIBRARIES = [
    "pydantic",
    "dash",
    "dash_mantine_components",
    "dash_iconify",
    "flask",
    "plotly",
    "pandas",
    "openpyxl",
]
DEFAULT_MAX_FILES = 5
DEFAULT_MAX_DESIGN_CHOICES = 3
# Phase 6 fixes (U6): how many AI clarifying questions one request may ask in Understand.
DEFAULT_MAX_MATERIAL_DECISIONS = 5
# Phase 5: folders that must exist in a CodeVision clone, and the biggest file the browser reads.
DEFAULT_WORKSPACE_MARKERS = ["src/web", "src/callbacks"]
DEFAULT_WORKSPACE_MAX_FILE_KB = 512
# Phase 6 (Build + test loop), spec section 11. Made-up starter values; real ones are set at work.
# The protected-file and approved-library lists are NOT repeated here: Build reuses the Phase 4
# lists so Approach and Build can never disagree (decision D-M).
DEFAULT_BUILD_MAX_ROUNDS = 3
DEFAULT_BUILD_TEST_TIMEOUT_SECONDS = 60
DEFAULT_BUILD_MAX_PROMPT_CHARS = 60000
DEFAULT_BUILD_MAX_PARALLEL = 2
# Phase 7 (Independent Tester), spec section 11. Made-up starter values.
DEFAULT_TESTER_MAX_PROMPT_CHARS = 60000
DEFAULT_TESTER_MAX_ATTEMPTS = 2
DEFAULT_TESTER_QUOTE_WINDOW = 2
# Phase 8 (Refine), spec section 12. Made-up starter values; real ones are set at work.
DEFAULT_REFINE_MAX_PER_REQUEST = 5
DEFAULT_REFINE_LANE_MAX_ATTEMPTS = 2
DEFAULT_REFINE_REPRO_MAX_ATTEMPTS = 2
DEFAULT_REFINE_CONFLICT_CONTEXT_LINES = 3
# Phase 9 (Enhance), spec section 13. Made-up starter values; real ones are set at work.
DEFAULT_ENHANCE_NAME_TOP_K = 5
DEFAULT_ENHANCE_MEANING_TOP_K = 3
DEFAULT_ENHANCE_FIND_MAX_ROUNDS = 3
DEFAULT_ENHANCE_MAX_KEEP_ITEMS = 8
DEFAULT_SAFETY_NET_MAX_TESTS = 20
DEFAULT_SAFETY_NET_MAX_ATTEMPTS = 2
DEFAULT_SAFETY_NET_MAX_CORRECTIONS = 2
DEFAULT_IMPACT_MAX_CALLERS = 30
DEFAULT_BUILD_BLOCKED_IMPORTS = [
    "subprocess",
    "socket",
    "ctypes",
    "multiprocessing",
    "urllib",
    "http",
    "requests",
    "ftplib",
    "smtplib",
    "telnetlib",
    "webbrowser",
]
DEFAULT_BUILD_SANDBOX_EXCLUDE = [".env", "*.db", ".git", "*.key", "*.pem"]
# Phase 11b: SonarQube severities (fixed) mapped to our three. Made-up defaults. Admin edits only
# the right-hand side; the keys are checked on save.
SONAR_SEVERITY_KEYS: tuple[str, ...] = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO")
DEFAULT_SONAR_SEVERITY_MAP: dict[str, str] = {
    "BLOCKER": "must_fix",
    "CRITICAL": "must_fix",
    "MAJOR": "should_fix",
    "MINOR": "fyi",
    "INFO": "fyi",
}


def _default_zones() -> list[FlagReviewZone]:
    return [
        FlagReviewZone(
            name="Security",
            description="Encryption, key handling, and permission checks.",
            examples=["Encrypting a customer field", "Checking a user's role"],
            path_patterns=["*security*", "*crypto*", "*permission*"],
        ),
        FlagReviewZone(
            name="Login",
            description="Sign-in, sessions, and passwords.",
            examples=["Login page", "Session timeout handling"],
            path_patterns=["*login*", "*session*", "*password*"],
        ),
    ]


class EscalationTrigger(_RulebookPart):
    # Plain text, not a fixed list of words, so a wrong name is reported by
    # find_rulebook_problems in plain words instead of as a Pydantic error.
    name: str
    on: bool


class Policy(_RulebookPart):
    # Retired by Phase 11 (spec section 9): nothing reads them. They stay optional so an old saved
    # version still loads, and are left out of every new save (see _drop_empty_retired_fields).
    default_level: Level | None = None
    max_level: Level | None = None
    never_generate_zones: list[NeverGenerateZone] = Field(default_factory=list)
    max_review_rounds: int | None = None
    escalation_triggers: list[EscalationTrigger]
    # Phase 11 (Admin console). Empty model name = use the .env model for that role (D-G).
    generator_model: str = ""
    tester_model: str = ""
    # Days an Unassigned file may wait before the Overview turns red (used by Phase 11c).
    admin_unassigned_stale_days: int = Field(default=14, ge=1, le=365)
    # Phase 10 (spec section 12). Defaults keep older rulebook versions loadable.
    # D-A: lock the developer's chat while an escalation is open.
    escalation_lock_chat: bool = True
    # Guard for the PR summary length: over it, the criteria list is cut to counts.
    handoff_summary_max_chars: int = Field(default=6000, ge=500, le=50000)
    # Phase 4 (Approach), spec section 7. Defaults keep older rulebook versions loadable.
    allowed_folders: list[str] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_FOLDERS))
    new_file_name_pattern: str = DEFAULT_NEW_FILE_NAME_PATTERN
    protected_files: list[str] = Field(default_factory=lambda: list(DEFAULT_PROTECTED_FILES))
    approved_libraries: list[str] = Field(
        default_factory=lambda: list(DEFAULT_APPROVED_LIBRARIES)
    )
    max_files: int = Field(default=DEFAULT_MAX_FILES, ge=1)
    max_design_choices: int = Field(default=DEFAULT_MAX_DESIGN_CHOICES, ge=1)
    # Phase 6 fixes (U6): moved here from a constant in Understand. 1 to 10, so a typo cannot
    # switch the questions off or make them endless.
    max_material_decisions: int = Field(default=DEFAULT_MAX_MATERIAL_DECISIONS, ge=1, le=15)
    flag_review_zones: list[FlagReviewZone] = Field(default_factory=_default_zones)
    # Phase 5 (Workspace), spec section 8. Same defaults idea: older versions still load.
    workspace_markers: list[str] = Field(default_factory=lambda: list(DEFAULT_WORKSPACE_MARKERS))
    workspace_max_file_kb: int = Field(default=DEFAULT_WORKSPACE_MAX_FILE_KB, ge=1)
    # Phase 6 (Build + test loop), spec section 11. Bounds stop a typo from making a build
    # endless (rounds, time limit) or unable to send anything (prompt size).
    build_max_rounds: int = Field(default=DEFAULT_BUILD_MAX_ROUNDS, ge=1, le=5)
    build_test_timeout_seconds: int = Field(
        default=DEFAULT_BUILD_TEST_TIMEOUT_SECONDS, ge=1, le=600
    )
    build_max_prompt_chars: int = Field(default=DEFAULT_BUILD_MAX_PROMPT_CHARS, ge=1000)
    build_max_parallel: int = Field(default=DEFAULT_BUILD_MAX_PARALLEL, ge=1, le=10)
    build_blocked_imports: list[str] = Field(
        default_factory=lambda: list(DEFAULT_BUILD_BLOCKED_IMPORTS)
    )
    build_sandbox_exclude: list[str] = Field(
        default_factory=lambda: list(DEFAULT_BUILD_SANDBOX_EXCLUDE)
    )
    # Phase 7 (Independent Tester), spec section 11. Separate from the build prompt size because
    # the Tester may run on another model with another server limit.
    tester_max_prompt_chars: int = Field(default=DEFAULT_TESTER_MAX_PROMPT_CHARS, ge=1000)
    tester_max_attempts: int = Field(default=DEFAULT_TESTER_MAX_ATTEMPTS, ge=1, le=5)
    tester_quote_window: int = Field(default=DEFAULT_TESTER_QUOTE_WINDOW, ge=0, le=10)
    # Phase 8 (Refine), spec section 12. Bounds keep a typo from making a loop endless.
    refine_max_per_request: int = Field(default=DEFAULT_REFINE_MAX_PER_REQUEST, ge=1, le=20)
    refine_lane_max_attempts: int = Field(default=DEFAULT_REFINE_LANE_MAX_ATTEMPTS, ge=1, le=5)
    refine_repro_max_attempts: int = Field(default=DEFAULT_REFINE_REPRO_MAX_ATTEMPTS, ge=1, le=5)
    refine_conflict_context_lines: int = Field(
        default=DEFAULT_REFINE_CONFLICT_CONTEXT_LINES, ge=0, le=10
    )
    # Phase 9 (Enhance), spec section 13. Bounds keep a typo from making a loop endless.
    enhance_name_top_k: int = Field(default=DEFAULT_ENHANCE_NAME_TOP_K, ge=1, le=20)
    enhance_meaning_top_k: int = Field(default=DEFAULT_ENHANCE_MEANING_TOP_K, ge=1, le=20)
    enhance_find_max_rounds: int = Field(default=DEFAULT_ENHANCE_FIND_MAX_ROUNDS, ge=1, le=10)
    enhance_max_keep_items: int = Field(default=DEFAULT_ENHANCE_MAX_KEEP_ITEMS, ge=1, le=20)
    safety_net_max_tests: int = Field(default=DEFAULT_SAFETY_NET_MAX_TESTS, ge=1, le=50)
    safety_net_max_attempts: int = Field(default=DEFAULT_SAFETY_NET_MAX_ATTEMPTS, ge=1, le=5)
    safety_net_max_corrections: int = Field(
        default=DEFAULT_SAFETY_NET_MAX_CORRECTIONS, ge=0, le=5
    )
    impact_max_callers: int = Field(default=DEFAULT_IMPACT_MAX_CALLERS, ge=1, le=200)
    # The catalog (D-B). Empty for a rulebook saved before Phase 9.
    capabilities: list[Capability] = Field(default_factory=list)
    # Phase 11b (D-F). Keys are checked by find_rulebook_problems, so a wrong key is reported in
    # plain words with the other problems.
    sonar_severity_map: dict[str, Severity] = Field(
        default_factory=lambda: dict(DEFAULT_SONAR_SEVERITY_MAP)
    )

    @field_validator("escalation_triggers")
    @classmethod
    def _map_old_triggers(cls, triggers: list[EscalationTrigger]) -> list[EscalationTrigger]:
        # D-K: an old version holds three triggers under old names. Map them, then add any of the
        # five that is missing as "on", so every loaded version has the same shape. Unknown or
        # repeated names are left alone for find_rulebook_problems to report.
        mapped = [
            EscalationTrigger(name=OLD_TRIGGER_NAMES.get(item.name, item.name), on=item.on)
            for item in triggers
        ]
        present = {item.name for item in mapped}
        for name in ESCALATION_TRIGGER_NAMES:
            if name not in present:
                mapped.append(EscalationTrigger(name=name, on=True))
        return mapped

    @model_serializer(mode="wrap")
    def _drop_empty_retired_fields(self, handler):
        data = handler(self)
        for name in RETIRED_POLICY_FIELDS:
            if not data.get(name):
                data.pop(name, None)
        return data

    @field_validator("new_file_name_pattern")
    @classmethod
    def _pattern_must_compile(cls, value: str) -> str:
        # A broken pattern would crash every file-plan check, so it is refused when loaded.
        try:
            re.compile(value)
        except re.error as error:
            raise ValueError(f"is not a valid regular expression ({error})") from error
        return value


class Rulebook(_RulebookPart):
    charter: Charter
    rules: list[Rule]
    policy: Policy
    # Phase 11b (D-H): stored only, not sent to any AI call. Empty for older versions.
    golden_examples: list[GoldenExample] = Field(default_factory=list)


class RulebookVersion(BaseModel):
    # frozen=True: a saved version cannot be changed in memory either (rule R1).
    model_config = ConfigDict(frozen=True)

    version_number: int = Field(ge=1)
    rulebook: Rulebook
    change_note: str = Field(min_length=1)
    saved_by: str = Field(min_length=1)
    saved_at: AwareDatetime
    # Empty unless this version was made by restoring an older one.
    restored_from: int | None = Field(default=None, ge=1)


class CharterSize(BaseModel):
    model_config = ConfigDict(frozen=True)

    characters: int
    percent: float
    status: CharterStatus


def rule_id_number(rule_id: str) -> int:
    """The number at the end of a rule ID: CV-PY-007 gives 7."""
    return int(rule_id.rsplit("-", 1)[1])


def format_rule_id(kind: str, number: int) -> str:
    return f"{RULE_ID_PREFIXES[kind]}-{number:03d}"


def kind_of_rule_id(rule_id: str) -> str:
    """Which kind of rule an ID belongs to, judged by its prefix (CV-PY or CV-UI)."""
    prefix = rule_id.rsplit("-", 1)[0]
    return next(kind for kind, known in RULE_ID_PREFIXES.items() if known == prefix)


def find_rulebook_problems(rulebook: Rulebook) -> list[str]:
    """Return every rule R3 problem in plain words. An empty list means the rulebook is fine."""
    return [
        *_judgement_count_problems(rulebook.rules),
        *_trigger_problems(rulebook.policy),
        *_zone_name_problems(rulebook.policy),
        *_capability_problems(rulebook.policy),
        *_sonar_map_problems(rulebook.policy),
        *_rule_id_problems(rulebook.rules),
    ]


def without_retired_fields(rulebook: Rulebook) -> Rulebook:
    """A copy of the rulebook with the retired Policy fields emptied (spec section 9).

    Used by save and restore, so a new version never carries them, even when the version it
    was made from is an old one.
    """
    policy = rulebook.policy.model_copy(
        update={
            "default_level": None,
            "max_level": None,
            "never_generate_zones": [],
            "max_review_rounds": None,
        }
    )
    return rulebook.model_copy(update={"policy": policy})


def check_charter_size(charter: Charter) -> CharterSize:
    """How big the charter is against the 6,000-character limit: green, amber, or red.

    Green is under 80%, amber is 80% to 100%, red is over 100%.
    A red charter can still be saved; this check only reports it.
    """
    characters = _charter_text_length(charter)
    # Compare whole numbers, not rounded percentages, so 80.0% is never mistaken for 79.99%.
    if characters > CHARTER_CHARACTER_LIMIT:
        status = "red"
    elif characters * 100 >= CHARTER_CHARACTER_LIMIT * CHARTER_AMBER_PERCENT:
        status = "amber"
    else:
        status = "green"
    percent = round(characters * 100 / CHARTER_CHARACTER_LIMIT, 1)
    return CharterSize(characters=characters, percent=percent, status=status)


def _charter_text_length(charter: Charter) -> int:
    # Only the text the Admin wrote counts, not brackets, quotes, or field names.
    texts = [
        charter.purpose,
        *charter.in_scope,
        *charter.out_of_scope,
        *charter.architecture_principles,
        *charter.constraints,
    ]
    for entry in charter.glossary:
        texts.extend([entry.term, entry.meaning])
    return sum(len(text) for text in texts)


def _judgement_count_problems(rules: list[Rule]) -> list[str]:
    count = sum(1 for rule in rules if rule.kind == "judgement")
    if count > MAX_JUDGEMENT_RULES:
        return [
            f"There are {count} judgement rules. The pilot allows at most {MAX_JUDGEMENT_RULES}."
        ]
    return []


def _trigger_problems(policy: Policy) -> list[str]:
    names = [trigger.name for trigger in policy.escalation_triggers]
    # Same names, each exactly once, in any order.
    if sorted(names) != sorted(ESCALATION_TRIGGER_NAMES):
        return [
            f"The escalation triggers must be exactly these {len(ESCALATION_TRIGGER_NAMES)}, "
            f"each listed once: {', '.join(ESCALATION_TRIGGER_NAMES)}. "
            f"Found: {', '.join(names) or 'none'}."
        ]
    return []


def _zone_name_problems(policy: Policy) -> list[str]:
    problems = []
    seen: set[str] = set()
    for zone in policy.flag_review_zones:
        key = zone.name.strip().lower()
        if key in seen:
            problems.append(f"Flag-for-review zone '{zone.name}' is listed more than once.")
        seen.add(key)
    return problems


def _capability_problems(policy: Policy) -> list[str]:
    problems = []
    seen: set[str] = set()
    for capability in policy.capabilities:
        key = capability.name.strip().lower()
        if key in seen:
            problems.append(f"Capability '{capability.name}' is listed more than once.")
        seen.add(key)
        if any(not pattern.strip() for pattern in capability.path_patterns):
            problems.append(f"Capability '{capability.name}' has an empty path pattern.")
    return problems


def _sonar_map_problems(policy: Policy) -> list[str]:
    keys = set(policy.sonar_severity_map)
    problems = []
    for key in SONAR_SEVERITY_KEYS:
        if key not in keys:
            problems.append(f"The SonarQube severity map is missing the key {key}.")
    for key in sorted(keys - set(SONAR_SEVERITY_KEYS)):
        problems.append(f"The SonarQube severity map has an unknown key {key}.")
    return problems


def _rule_id_problems(rules: list[Rule]) -> list[str]:
    problems = []
    seen: set[str] = set()
    reported: set[str] = set()
    for rule in rules:
        if rule.rule_id in seen and rule.rule_id not in reported:
            problems.append(f"Rule ID {rule.rule_id} is used by more than one rule.")
            reported.add(rule.rule_id)
        seen.add(rule.rule_id)

        expected_prefix = RULE_ID_PREFIXES[rule.kind]
        if not rule.rule_id.startswith(expected_prefix + "-"):
            problems.append(
                f"Rule {rule.rule_id} is a {rule.kind} rule, "
                f"so its ID must start with {expected_prefix}."
            )
    return problems
