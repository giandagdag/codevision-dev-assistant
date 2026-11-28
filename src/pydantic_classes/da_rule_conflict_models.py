"""Fix G9: one rule conflict. Kept apart so the session and the checks can both import it."""

from dataclasses import dataclass

TEXT_MAX = 200


@dataclass(frozen=True)
class RuleConflict:
    criterion: str  # "AC-2", "SUMMARY" or "DD-1"
    rule: str  # rule ID, CHARTER:out_of_scope:n, LIB:name or ZONE:name
    why: str
    fix: str
    title: str = ""  # the rule's title, filled in by the app for the chat line

    def cut(self) -> RuleConflict:
        return RuleConflict(
            self.criterion, self.rule, self.why[:TEXT_MAX], self.fix[:TEXT_MAX], self.title
        )


GAP_CASE_MAX, GAP_QUESTION_MAX, GAP_CRITERION_MAX = 120, 200, 250
GAP_LIMIT = 5


@dataclass(frozen=True)
class Gap:
    """Fix G9 F1: an input or situation no criterion covers, found by the rule check call."""

    case: str  # e.g. "no arguments"
    question: str  # what should happen?
    suggested_criterion: str  # "Given ..., when ..., then ..."

    def cut(self) -> Gap:
        return Gap(
            self.case[:GAP_CASE_MAX],
            self.question[:GAP_QUESTION_MAX],
            self.suggested_criterion[:GAP_CRITERION_MAX],
        )
