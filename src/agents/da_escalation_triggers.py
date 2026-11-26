"""The five escalation triggers (Phase 10 spec section 7). Plain code, no AI, no database.

Each function takes the request's PINNED trigger switches (`policy.escalation_triggers`) and the
facts it needs, and answers with a TriggerDecision: fire with this reason, stay quiet, or "the
switch is off" (the caller audits `escalation_switched_off`). The hooks that call them arrive in
step 7. AS400 picture: a monitor job that raises a message when a condition is met.
"""

from agents.da_understand_checks import SCOPE_CONFLICT_PREFIX
from pydantic_classes.da_escalation_models import EscalationRow, TriggerDecision
from pydantic_classes.da_models import STATUS_ESCALATION, STATUS_HANDED_OFF
from pydantic_classes.da_rulebook_models import EscalationTrigger

CAP_HIT_TWICE = "cap_hit_twice"
OUT_OF_SCOPE = "out_of_scope"
DISPUTE = "dispute"
TESTER_UNABLE_TWICE = "tester_unable_twice"
GET_HELP = "get_help"
RULE_EXCEPTION = "rule_exception"  # Fix G9 U6

DISPUTE_OFF_MESSAGE = "Disputes are not routed to a senior at the moment. Get help instead."
GET_HELP_OFF_MESSAGE = (
    "Get help is not routed to a senior at the moment. Ask your senior directly."
)

_TWICE = 2


def trigger_on(triggers: list[EscalationTrigger], name: str) -> bool:
    return any(item.name == name and item.on for item in triggers)


def _decide(
    triggers: list[EscalationTrigger], name: str, reason: str, count: int = 0
) -> TriggerDecision:
    """The condition is met: fire if the switch is on, else report it as switched off."""
    if trigger_on(triggers, name):
        return TriggerDecision(trigger=name, fire=True, reason=reason, count=count)
    return TriggerDecision(trigger=name, switched_off=True, reason=reason, count=count)


def _quiet(name: str) -> TriggerDecision:
    return TriggerDecision(trigger=name)


def reaches_twice(count: int, last_fired: int) -> bool:
    """Rule X2: fire at 2, and again only 2 later than the count that fired last (0 = never)."""
    return count >= _TWICE and count >= last_fired + _TWICE


def status_blocks_triggers(status: str) -> bool:
    """Rule X4: nothing fires at HANDED_OFF, or at a request already at ESCALATION_REQUIRED."""
    return status in (STATUS_HANDED_OFF, STATUS_ESCALATION)


# 1. Two builds in a row ended NOT_PASSING.
def cap_hit_twice(
    triggers: list[EscalationTrigger], not_passing_in_a_row: int, build_number: int, last_fired: int
) -> TriggerDecision:
    """`last_fired` must leave out returned rows: Return reset the count (spec section 10)."""
    if not reaches_twice(not_passing_in_a_row, last_fired):
        return _quiet(CAP_HIT_TWICE)
    reason = f"Round cap hit twice: builds {build_number - 1} and {build_number}"
    return _decide(triggers, CAP_HIT_TWICE, reason, not_passing_in_a_row)


# 2a. The confirmed record still carries a scope conflict.
def out_of_scope_understand(
    triggers: list[EscalationTrigger], open_items: list[str]
) -> TriggerDecision:
    for item in open_items:
        if item.startswith(SCOPE_CONFLICT_PREFIX):
            conflict = item[len(SCOPE_CONFLICT_PREFIX) :].strip()
            return _decide(triggers, OUT_OF_SCOPE, f"Out of scope: {conflict}")
    return _quiet(OUT_OF_SCOPE)


# 2b. The file plan needs a protected or out-of-folder path and the change cap (G9) is used up.
def out_of_scope_approach(
    triggers: list[EscalationTrigger],
    offending_paths: list[str],
    change_count: int,
    max_changes: int,
) -> TriggerDecision:
    """Plain code decides scope, never the AI (D-H). With the cap not used up, the developer can
    still change the plan, so nothing fires."""
    if not offending_paths or change_count < max_changes:
        return _quiet(OUT_OF_SCOPE)
    return _decide(triggers, OUT_OF_SCOPE, f"Out of scope: {offending_paths[0]}")


# 3. The developer disputed a Must fix.
def dispute(triggers: list[EscalationTrigger], finding_id: str) -> TriggerDecision:
    return _decide(triggers, DISPUTE, f"Disputed Must fix: {finding_id}")


# 4. Two reviews of this request ended Unable to assess.
def tester_unable_twice(
    triggers: list[EscalationTrigger], unable_review_numbers: list[int], last_fired: int
) -> TriggerDecision:
    count = len(unable_review_numbers)
    if not reaches_twice(count, last_fired):
        return _quiet(TESTER_UNABLE_TWICE)
    first, second = unable_review_numbers[-2], unable_review_numbers[-1]
    reason = f"Tester unable to assess twice: reviews {first} and {second}"
    return _decide(triggers, TESTER_UNABLE_TWICE, reason, count)


# 5. Any Get help button.
def get_help(triggers: list[EscalationTrigger], stage: str, step: str) -> TriggerDecision:
    return _decide(triggers, GET_HELP, f"Escalated in {stage}: {step}")


# 6. Ask for an exception (Fix G9 U6). No switch in the rulebook counts as ON: never silently off.
def rule_exception(triggers: list[EscalationTrigger], reason: str) -> TriggerDecision:
    if any(item.name == RULE_EXCEPTION and not item.on for item in triggers):
        return TriggerDecision(trigger=RULE_EXCEPTION, switched_off=True, reason=reason)
    return TriggerDecision(trigger=RULE_EXCEPTION, fire=True, reason=reason)


def add_reason(row: EscalationRow, trigger: str, reason: str) -> EscalationRow:
    """Rule X1: a second trigger on an open row adds a line instead of a second row."""
    reasons = row.reasons if reason in row.reasons else [*row.reasons, reason]
    triggers = row.triggers if trigger in row.triggers else [*row.triggers, trigger]
    return row.model_copy(update={"reasons": reasons, "triggers": triggers})
