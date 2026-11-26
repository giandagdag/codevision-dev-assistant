"""Fix G9 Part 1: where a request breaks the rulebook (U3, U4). Plain code, no AI.

The same shape serves the plain checks here and the AI rule check (next step): the app keeps only
conflicts that cite a real rule and a real place in the record.
"""

import re
from dataclasses import dataclass

from agents.da_approach_checks import library_name
from da_logging import get_logger
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Rulebook

logger = get_logger(__name__)

TEXT_MAX = 200
SUMMARY = "SUMMARY"

# "import requests", "the requests library", "package foo": a library named on purpose.
# Only "import X" names what follows; "library and ..." would catch ordinary words.
_LIBRARY_AFTER = re.compile(r"\bimport\s+([A-Za-z_][\w.-]*)", re.I)
_LIBRARY_BEFORE = re.compile(r"\b([A-Za-z_][\w-]*)\s+(?:library|package|module)\b", re.I)
_FILLER = frozenset({"the", "a", "an", "this", "that", "new", "python", "standard", "of"})


@dataclass(frozen=True)
class RuleConflict:
    criterion: str  # "AC-2", "SUMMARY" or "DD-1"
    rule: str  # rule ID, CHARTER:out_of_scope:n, LIB:name or ZONE:name
    why: str
    fix: str

    def cut(self) -> RuleConflict:
        return RuleConflict(
            self.criterion, self.rule, self.why[:TEXT_MAX], self.fix[:TEXT_MAX]
        )


LIST_CUT = 12  # long lists are cut with a count note, like the tagger


def rulebook_text(rulebook: Rulebook) -> str:
    """The whole rulebook as plain lines for a prompt (U1). Never holds a senior's name."""
    charter, policy = rulebook.charter, rulebook.policy
    judgement = [r for r in rulebook.rules if r.kind == "judgement"]
    sections = {
        "Constraints": charter.constraints,
        "Architecture principles": charter.architecture_principles,
        "Judgement rules": [f"{r.rule_id} {r.title}: {r.why}" for r in judgement],
        "Approved libraries": policy.approved_libraries,
        "Blocked imports": policy.build_blocked_imports,
        "Flag-for-review zones": [f"{z.name}: {z.description}" for z in policy.flag_review_zones],
    }
    lines = []
    for title, items in sections.items():
        lines.append(f"{title}:")
        lines += [f"- {item}" for item in items[:LIST_CUT]] or ["- (none)"]
        if len(items) > LIST_CUT:
            lines.append(f"- (and {len(items) - LIST_CUT} more not shown)")
    return "\n".join(lines)


def texts_of(record: RequestRecord) -> dict[str, str]:
    """The places a conflict can point at: SUMMARY, each AC-n and each DD-n."""
    places = {
        SUMMARY: "\n".join(
            [record.title, record.objective, record.expected_behaviour, *record.functional_flow]
        )
    }
    for item in record.acceptance_criteria:
        places[item.id] = f"{item.given}\n{item.when}\n{item.then}"
    for number, decision in enumerate(record.decisions, 1):
        places[f"DD-{number}"] = f"{decision.question}\n{decision.choice}"
    return places


def plain_conflicts(record: RequestRecord, rulebook: Rulebook) -> list[RuleConflict]:
    """Blocked imports, libraries off the approved list, and out-of-scope items (U3)."""
    found: list[RuleConflict] = []
    policy = rulebook.policy
    blocked = {library_name(name) for name in policy.build_blocked_imports}
    approved = {library_name(name) for name in policy.approved_libraries}
    out_of_scope = [_bag(item) for item in rulebook.charter.out_of_scope]
    for place, text in texts_of(record).items():
        words = {library_name(w) for w in re.findall(r"[A-Za-z_][\w-]*", text)}
        for name in sorted(blocked & words):
            found.append(
                RuleConflict(
                    place,
                    f"LIB:{name}",
                    f"'{name}' is a blocked import.",
                    f"Describe the need without {name}.",
                )
            )
        for name in _named_libraries(text) - blocked:
            if name.split(".")[0] not in approved:
                found.append(
                    RuleConflict(
                        place,
                        f"LIB:{name}",
                        f"'{name}' is not on the approved library list.",
                        "Use only approved libraries or the standard library.",
                    )
                )
        bag = _bag(text)
        for number, item in enumerate(out_of_scope, 1):
            if item and item <= bag:
                found.append(
                    RuleConflict(
                        place,
                        f"CHARTER:out_of_scope:{number}",
                        "The text covers an out-of-scope item: "
                        f"{rulebook.charter.out_of_scope[number - 1]}.",
                        "Remove the out-of-scope part from the request.",
                    )
                )
    return [conflict.cut() for conflict in found]


def keep_real_conflicts(
    conflicts: list[RuleConflict], record: RequestRecord, rulebook: Rulebook
) -> list[RuleConflict]:
    """Keep a conflict only when the cited rule and the place exist (U4). Others are dropped and
    only their count and kind are logged, never the AI's text."""
    places = set(texts_of(record))
    kept: list[RuleConflict] = []
    dropped: list[str] = []
    for conflict in conflicts:
        if conflict.criterion not in places:
            dropped.append("unknown place")
        elif not _rule_exists(conflict.rule, rulebook):
            dropped.append("unknown rule")
        else:
            kept.append(conflict.cut())
    if dropped:
        logger.warning("Rule check: dropped %s conflicts (%s)", len(dropped), sorted(set(dropped)))
    return kept


def _rule_exists(rule: str, rulebook: Rulebook) -> bool:
    kind, _, rest = rule.partition(":")
    if not rest:
        return rule in {item.rule_id for item in rulebook.rules}
    if kind == "CHARTER":
        _, _, number = rest.partition(":")
        return rest.startswith("out_of_scope:") and number.isdigit() and (
            1 <= int(number) <= len(rulebook.charter.out_of_scope)
        )
    if kind == "LIB":
        return True  # a library name needs no list: any named library can be refused
    if kind == "ZONE":
        return rest in {zone.name for zone in rulebook.policy.flag_review_zones}
    return False


def _named_libraries(text: str) -> set[str]:
    names = {library_name(m) for m in _LIBRARY_AFTER.findall(text)}
    names |= {library_name(m) for m in _LIBRARY_BEFORE.findall(text)}
    return {name for name in names if name not in _FILLER}


def _bag(text: str) -> frozenset[str]:
    """The words of a text, lower case, no order: an out-of-scope item matches in any order."""
    return frozenset(re.findall(r"\w+", text.lower()))
