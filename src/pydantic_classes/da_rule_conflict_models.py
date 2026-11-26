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
