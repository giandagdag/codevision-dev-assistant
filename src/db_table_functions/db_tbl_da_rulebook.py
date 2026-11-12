"""Save and read rulebook versions. Append-only: there are no edit or delete functions (rule R1).

Like journal receivers: every save is a new version (v1, v2, v3...), old versions are never
overwritten, and the active version is always the newest one.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from da_logging import get_logger
from db_table_functions.da_db import begin_write, open_db, to_db_time
from pydantic_classes.da_rulebook_models import (
    RULE_ID_PREFIXES,
    Rulebook,
    RulebookVersion,
    check_charter_size,
    find_rulebook_problems,
    format_rule_id,
    kind_of_rule_id,
    rule_id_number,
    without_retired_fields,
)

logger = get_logger(__name__)

SEED_RULEBOOK_FILE = Path(__file__).resolve().parents[1] / "data" / "da_rulebook_seed.json"

# The triggers make the database itself refuse any edit or delete, even from code that skips
# this file. They are SQLite-only: CodeVision's database will need its own equivalent.
#
# Rule ID counters hold the last number handed out per kind. Numbers come from here, not from
# "highest number plus one", so a deleted rule's number is never reused (rule R7).
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS da_rulebook_versions (
    version_number INTEGER PRIMARY KEY,
    rulebook       TEXT NOT NULL,
    change_note    TEXT NOT NULL,
    saved_by       TEXT NOT NULL,
    saved_at       TEXT NOT NULL,
    restored_from  INTEGER REFERENCES da_rulebook_versions (version_number)
);

CREATE TRIGGER IF NOT EXISTS da_rulebook_versions_no_update
BEFORE UPDATE ON da_rulebook_versions
BEGIN
    SELECT RAISE(ABORT, 'Rulebook versions are append-only and cannot be edited.');
END;

CREATE TRIGGER IF NOT EXISTS da_rulebook_versions_no_delete
BEFORE DELETE ON da_rulebook_versions
BEGIN
    SELECT RAISE(ABORT, 'Rulebook versions are append-only and cannot be deleted.');
END;

CREATE TABLE IF NOT EXISTS da_rule_id_counters (
    kind        TEXT PRIMARY KEY,
    last_number INTEGER NOT NULL
);
"""


class RulebookError(Exception):
    """A rulebook action was refused. The message says why in plain words."""


class StaleSaveError(RulebookError):
    """Someone else saved a newer version first (rule R4)."""


def ensure_rulebook_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_CREATE_TABLES_SQL)


def load_rulebook_file(path: Path) -> Rulebook:
    """Read a rulebook from a JSON file, such as the seed. Problems come back as plain messages."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RulebookError(f"Rulebook file {path} was not found.") from error
    except json.JSONDecodeError as error:
        raise RulebookError(
            f"Rulebook file {path} is not valid JSON (line {error.lineno}): {error.msg}."
        ) from error
    try:
        return Rulebook.model_validate(data)
    except ValidationError as error:
        raise RulebookError(
            f"Rulebook file {path} has problems:\n{_describe_shape_errors(error)}"
        ) from error


def publish_first_version(
    db_path: Path, rulebook: Rulebook, saved_by: str, note: str, now: datetime | None = None
) -> RulebookVersion:
    """Create v1. Refused if any version already exists."""
    _check_saved_by_and_note(saved_by, note)
    with open_db(db_path) as conn:
        ensure_rulebook_tables(conn)
        begin_write(conn)
        active = _active_version(conn)
        if active is not None:
            raise RulebookError(
                f"A rulebook is already published (active version v{active.version_number}). "
                "Use save_new_version to change it."
            )
        _refuse_if_problems(find_rulebook_problems(rulebook))
        # v1 is where the counters start: its own IDs count as handed out.
        _raise_counters_to_cover(conn, rulebook)
        version = _insert_version(conn, 1, rulebook, saved_by, note, now, restored_from=None)
    return version


def save_new_version(
    db_path: Path,
    rulebook: Rulebook,
    base_version: int,
    saved_by: str,
    note: str,
    now: datetime | None = None,
) -> RulebookVersion:
    """Save the rulebook as the next version.

    base_version is the version the Admin started editing from. If someone saved a newer one
    in the meantime, the save is refused so their work is not silently overwritten (rule R4).
    """
    _check_saved_by_and_note(saved_by, note)
    # A new version never carries the retired fields, even when it was edited from an old one.
    rulebook = without_retired_fields(rulebook)
    with open_db(db_path) as conn:
        ensure_rulebook_tables(conn)
        begin_write(conn)
        active = _require_active_version(conn)
        if base_version != active.version_number:
            raise StaleSaveError(
                f"Your changes are based on v{base_version}, but v{active.version_number} "
                f"is now the active version (someone saved first). "
                f"Reload v{active.version_number}, redo your changes, and save again."
            )
        _refuse_if_problems(
            find_rulebook_problems(rulebook) + _ids_not_handed_out(conn, rulebook)
        )
        _refuse_if_unchanged(rulebook, active)
        version = _insert_version(
            conn, active.version_number + 1, rulebook, saved_by, note, now, restored_from=None
        )
    return version


def restore_version(
    db_path: Path,
    number: int,
    saved_by: str,
    note: str | None = None,
    now: datetime | None = None,
) -> RulebookVersion:
    """Copy an old version into a new version. Nothing is lost: the old one stays as it was."""
    if note is None:
        note = f"Restored from v{number}"
    _check_saved_by_and_note(saved_by, note)
    with open_db(db_path) as conn:
        ensure_rulebook_tables(conn)
        begin_write(conn)
        active = _require_active_version(conn)
        source = _version_by_number(conn, number)
        if source is None:
            raise RulebookError(
                f"Version v{number} does not exist. "
                f"The newest version is v{active.version_number}."
            )
        if number == active.version_number:
            raise RulebookError(
                f"v{number} is already the active version, so there is nothing to restore."
            )
        # The copy is the new shape: five triggers (mapped on load) and no retired fields.
        restored = without_retired_fields(source.rulebook)
        # Old versions passed these checks when saved, but check again in case the rules
        # have tightened since. The restore is refused rather than bringing back a bad rulebook.
        _refuse_if_problems(find_rulebook_problems(restored) + _ids_not_handed_out(conn, restored))
        _refuse_if_unchanged(restored, active)
        version = _insert_version(
            conn,
            active.version_number + 1,
            restored,
            saved_by,
            note,
            now,
            restored_from=number,
        )
    return version


def get_active_version(db_path: Path) -> RulebookVersion | None:
    """Return the newest version, or None if no rulebook has been published yet."""
    with open_db(db_path) as conn:
        ensure_rulebook_tables(conn)
        return _active_version(conn)


def get_active_version_number(conn: sqlite3.Connection) -> int | None:
    """The active version number, read on the caller's connection (used when pinning requests).

    The caller runs ensure_rulebook_tables first, before taking the write lock: setting up
    tables would end the caller's transaction.
    """
    row = conn.execute("SELECT MAX(version_number) AS newest FROM da_rulebook_versions").fetchone()
    return row["newest"]


def get_version(db_path: Path, number: int) -> RulebookVersion | None:
    """Return version `number`, or None if there is no such version."""
    with open_db(db_path) as conn:
        ensure_rulebook_tables(conn)
        return _version_by_number(conn, number)


def list_versions(db_path: Path) -> list[RulebookVersion]:
    """Return every version, newest first."""
    with open_db(db_path) as conn:
        ensure_rulebook_tables(conn)
        rows = conn.execute(
            "SELECT * FROM da_rulebook_versions ORDER BY version_number DESC"
        ).fetchall()
    return [_version_from_row(row) for row in rows]


def next_rule_id(db_path: Path, kind: str) -> str:
    """Hand out the next unused rule ID for this kind, such as CV-PY-006.

    The number is used up as soon as it is handed out, even if the rule is never saved,
    the same way request numbers work. So a number can never be given out twice.
    """
    if kind not in RULE_ID_PREFIXES:
        raise RulebookError(
            f"Rule kind '{kind}' is not allowed. Use one of: {', '.join(RULE_ID_PREFIXES)}."
        )
    with open_db(db_path) as conn:
        ensure_rulebook_tables(conn)
        row = conn.execute(
            "INSERT INTO da_rule_id_counters (kind, last_number) VALUES (?, 1)"
            " ON CONFLICT(kind) DO UPDATE SET last_number = last_number + 1"
            " RETURNING last_number",
            (kind,),
        ).fetchone()
    return format_rule_id(kind, row["last_number"])


def _check_saved_by_and_note(saved_by: str, note: str) -> None:
    if not saved_by or not saved_by.strip():
        raise RulebookError("Saved by is empty. Give the user ID of the person saving.")
    if not note or not note.strip():
        raise RulebookError(
            "The change note is empty. Say in a few words what changed and why, then save again."
        )


def _refuse_if_problems(problems: list[str]) -> None:
    if problems:
        listed = "\n".join(f"- {problem}" for problem in problems)
        raise RulebookError(f"The rulebook was not saved. Please fix these problems:\n{listed}")


def _refuse_if_unchanged(rulebook: Rulebook, active: RulebookVersion) -> None:
    # Compare without the retired fields, so an old-shape active version does not make an
    # unchanged form look like a change.
    if rulebook == without_retired_fields(active.rulebook):
        raise RulebookError(
            f"No changes to save. The rulebook is the same as the active version "
            f"v{active.version_number}."
        )


def _ids_not_handed_out(conn: sqlite3.Connection, rulebook: Rulebook) -> list[str]:
    # After v1, new IDs must come from next_rule_id, so an ID above the counter was typed by hand.
    problems = []
    for rule in rulebook.rules:
        if rule_id_number(rule.rule_id) > _counter(conn, kind_of_rule_id(rule.rule_id)):
            problems.append(
                f"Rule ID {rule.rule_id} has not been handed out yet. "
                "Use next_rule_id to get a new rule ID."
            )
    return problems


def _counter(conn: sqlite3.Connection, kind: str) -> int:
    row = conn.execute(
        "SELECT last_number FROM da_rule_id_counters WHERE kind = ?", (kind,)
    ).fetchone()
    return row["last_number"] if row else 0


def _raise_counters_to_cover(conn: sqlite3.Connection, rulebook: Rulebook) -> None:
    # Only ever raises a counter, never lowers it, so no number is handed out twice.
    highest: dict[str, int] = {}
    for rule in rulebook.rules:
        kind = kind_of_rule_id(rule.rule_id)
        highest[kind] = max(highest.get(kind, 0), rule_id_number(rule.rule_id))
    for kind, number in highest.items():
        conn.execute(
            "INSERT INTO da_rule_id_counters (kind, last_number) VALUES (?, ?)"
            " ON CONFLICT(kind) DO UPDATE SET last_number = MAX(last_number, excluded.last_number)",
            (kind, number),
        )


def _insert_version(
    conn: sqlite3.Connection,
    number: int,
    rulebook: Rulebook,
    saved_by: str,
    note: str,
    now: datetime | None,
    restored_from: int | None,
) -> RulebookVersion:
    version = RulebookVersion(
        version_number=number,
        rulebook=rulebook,
        change_note=note.strip(),
        saved_by=saved_by.strip(),
        saved_at=now or datetime.now(UTC),
        restored_from=restored_from,
    )
    conn.execute(
        "INSERT INTO da_rulebook_versions (version_number, rulebook, change_note, saved_by,"
        " saved_at, restored_from) VALUES (?, ?, ?, ?, ?, ?)",
        (
            version.version_number,
            version.rulebook.model_dump_json(),
            version.change_note,
            version.saved_by,
            to_db_time(version.saved_at),
            version.restored_from,
        ),
    )
    size = check_charter_size(rulebook.charter)
    if size.status == "red":
        logger.warning(
            "Rulebook v%s saved with a red charter (%s%% of the limit).", number, size.percent
        )
    logger.info("Saved rulebook v%s", number)
    return version


def _active_version(conn: sqlite3.Connection) -> RulebookVersion | None:
    row = conn.execute(
        "SELECT * FROM da_rulebook_versions ORDER BY version_number DESC LIMIT 1"
    ).fetchone()
    return _version_from_row(row) if row else None


def _require_active_version(conn: sqlite3.Connection) -> RulebookVersion:
    active = _active_version(conn)
    if active is None:
        raise RulebookError(
            "No rulebook has been published yet. Use publish_first_version to create v1."
        )
    return active


def _version_by_number(conn: sqlite3.Connection, number: int) -> RulebookVersion | None:
    row = conn.execute(
        "SELECT * FROM da_rulebook_versions WHERE version_number = ?", (number,)
    ).fetchone()
    return _version_from_row(row) if row else None


def _version_from_row(row: sqlite3.Row) -> RulebookVersion:
    return RulebookVersion(
        **{**dict(row), "rulebook": Rulebook.model_validate_json(row["rulebook"])}
    )


def _describe_shape_errors(error: ValidationError) -> str:
    lines = []
    for problem in error.errors():
        where = ".".join(str(part) for part in problem["loc"]) or "(top level)"
        lines.append(f"- {where}: {problem['msg']}")
    return "\n".join(lines)
