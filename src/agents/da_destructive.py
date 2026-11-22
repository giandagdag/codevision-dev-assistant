"""Fix G5 P5: allowed destructive data work continues only with four things in the request.

1 a business reason, 2 a named list of tables or objects (never "all"), 3 a backup or rollback step
as an acceptance criterion, 4 the work marked as the review zone "Destructive data change" (the app
does that itself: see compute_warnings). Plain code, no AI. Each missing item is asked as an open
decision that only a senior may answer (never assumed, like security in B2 S7).
"""

import re

from pydantic_classes.da_request_record_models import PendingDecision, RequestRecord

DESTRUCTIVE_ZONE = "Destructive data change"
_ALL_WORDS = re.compile(r"\b(all|every|entire|whole|any)\b", re.IGNORECASE)
_BACKUP_WORDS = ("backup", "back up", "rollback", "roll back", "restore")

# Each question holds the word "destructive", so it is on the never-assume list.
Q_REASON = "Destructive data change: what is the business reason for removing this data?"
Q_NAMES = "Destructive data change: which named tables or objects are removed? (never all)"
Q_BACKUP = "Destructive data change: what backup or rollback step is an acceptance criterion?"
OPTIONS = ["Covered, I checked the request", "Not covered, the request must change"]


def missing_questions(record: RequestRecord) -> list[str]:
    """The questions for the items this record does not have yet."""
    missing = []
    if not record.reason.strip():
        missing.append(Q_REASON)
    if not record.in_scope or any(_ALL_WORDS.search(item) for item in record.in_scope):
        missing.append(Q_NAMES)
    criteria = " ".join(f"{c.given} {c.when} {c.then}" for c in record.acceptance_criteria)
    if not any(word in criteria.lower() for word in _BACKUP_WORDS):
        missing.append(Q_BACKUP)
    return missing


def pending_for(record: RequestRecord) -> list[PendingDecision]:
    """The open decisions to add (none that the record already holds as an open item)."""
    return [
        PendingDecision(question=question, options=OPTIONS)
        for question in missing_questions(record)
    ]
