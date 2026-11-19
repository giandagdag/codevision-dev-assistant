"""Admin audit log for events that belong to no request (Upgrade G: index rollback, tag restore).

AS400 picture: a journal entry. Append-only JSON next to the index. The request audit table needs a
request id, so it cannot hold these. Holds who, when and one line of words, never code text.
"""

import json
from datetime import datetime
from pathlib import Path

from agents.da_admin_index import index_dir

AUDIT_NAME = "da_admin_audit.json"
INDEX_ROLLED_BACK = "index_rolled_back"
TAGS_RESTORED = "tags_restored"


def add_admin_event(
    kind: str, who: str, text: str, directory: Path | None = None, now: datetime | None = None
) -> None:
    events = read_admin_events(directory)
    events.append({
        "kind": kind, "who": who, "text": text,
        "at": (now or datetime.now()).isoformat(timespec="seconds"),
    })
    path = (directory or index_dir()) / AUDIT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, indent=1), encoding="utf-8")


def read_admin_events(directory: Path | None = None) -> list[dict]:
    """Oldest first. A missing or damaged file is an empty list."""
    try:
        events = json.loads(((directory or index_dir()) / AUDIT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in events if isinstance(e, dict)] if isinstance(events, list) else []
