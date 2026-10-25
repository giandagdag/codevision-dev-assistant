"""Data shapes for the rulebook, and the checks a rulebook must pass before it is saved.

Pydantic checks the shape (field types and allowed words). find_rulebook_problems checks the
house rules from spec rule R3 and returns every problem as a plain sentence, so an Admin sees
the whole list at once instead of fixing one error per attempt.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

RuleKind = Literal["judgement", "ui_convention"]
Severity = Literal["must_fix", "should_fix", "fyi"]
Level = Literal["L0", "L1", "L2", "L3"]
CharterStatus = Literal["green", "amber", "red"]

# Lowest to highest, so a level's position says how high it is.
LEVELS: tuple[str, ...] = ("L0", "L1", "L2", "L3")
LOCKED_LEVEL = "L3"

RULE_ID_PREFIXES: dict[str, str] = {"judgement": "CV-PY", "ui_convention": "CV-UI"}
# Three or more digits, so rule 1000 still fits.
RULE_ID_PATTERN = r"^CV-(PY|UI)-\d{3,}$"

MAX_JUDGEMENT_RULES = 10
MIN_REVIEW_ROUNDS = 1
MAX_REVIEW_ROUNDS = 5

ESCALATION_TRIGGER_NAMES: tuple[str, ...] = (
    "max_rounds_with_must_fix_open",
    "out_of_scope",
    "developer_disputes_finding",
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


class EscalationTrigger(_RulebookPart):
    # Plain text, not a fixed list of words, so a wrong name is reported by
    # find_rulebook_problems in plain words instead of as a Pydantic error.
    name: str
    on: bool


class Policy(_RulebookPart):
    default_level: Level
    max_level: Level
    never_generate_zones: list[NeverGenerateZone]
    # A plain whole number here; the 1 to 5 range is checked by find_rulebook_problems.
    max_review_rounds: int
    escalation_triggers: list[EscalationTrigger]


class Rulebook(_RulebookPart):
    charter: Charter
    rules: list[Rule]
    policy: Policy


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
        *_level_problems(rulebook.policy),
        *_judgement_count_problems(rulebook.rules),
        *_review_round_problems(rulebook.policy),
        *_trigger_problems(rulebook.policy),
        *_rule_id_problems(rulebook.rules),
    ]


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


def _level_problems(policy: Policy) -> list[str]:
    problems = []
    if LEVELS.index(policy.default_level) > LEVELS.index(policy.max_level):
        problems.append(
            f"The default level {policy.default_level} is higher than "
            f"the max level {policy.max_level}."
        )
    for label, level in (("default level", policy.default_level), ("max level", policy.max_level)):
        if level == LOCKED_LEVEL:
            problems.append(
                f"The {label} is {LOCKED_LEVEL}, which is locked for the pilot. "
                "Use L0, L1, or L2."
            )
    return problems


def _judgement_count_problems(rules: list[Rule]) -> list[str]:
    count = sum(1 for rule in rules if rule.kind == "judgement")
    if count > MAX_JUDGEMENT_RULES:
        return [
            f"There are {count} judgement rules. The pilot allows at most {MAX_JUDGEMENT_RULES}."
        ]
    return []


def _review_round_problems(policy: Policy) -> list[str]:
    rounds = policy.max_review_rounds
    if not MIN_REVIEW_ROUNDS <= rounds <= MAX_REVIEW_ROUNDS:
        return [
            f"Max review rounds is {rounds}. "
            f"It must be a whole number from {MIN_REVIEW_ROUNDS} to {MAX_REVIEW_ROUNDS}."
        ]
    return []


def _trigger_problems(policy: Policy) -> list[str]:
    names = [trigger.name for trigger in policy.escalation_triggers]
    # Same names, each exactly once, in any order.
    if sorted(names) != sorted(ESCALATION_TRIGGER_NAMES):
        return [
            "The escalation triggers must be exactly these 3, each listed once: "
            f"{', '.join(ESCALATION_TRIGGER_NAMES)}. "
            f"Found: {', '.join(names) or 'none'}."
        ]
    return []


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
