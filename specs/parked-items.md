# Parked items

Small items found in the Phase 0 and Phase 1 work and deliberately left for later. None of them blocks the current phase.

| # | Item | Why it is parked | When to fix |
|---|---|---|---|
| P1 | Table setup runs on every database call (`executescript` in `db_tbl_da_requests.py`, `db_tbl_da_audit.py`, and, since Phase 1, `db_tbl_da_rulebook.py`) | It works and costs little on SQLite, and this code changes anyway when we move to CodeVision's database | Before the code is copied into CodeVision, as part of the database switch (Q2) |
| P2 | Swap `da_logging.py` for CodeVision's shared logger | We don't yet know whether CodeVision has one (spec question Q4) | Once Q4 is answered, before the move to CodeVision |
| P3 | Audit details that refer back to themselves raise a raw `ValueError` instead of our plain message (`add_audit_event` in `db_tbl_da_audit.py`) | Very unlikely: our own code never builds such details | When a later phase starts passing richer details, or in any phase that touches the audit file |
| P4 | A retired rule ID re-typed by hand for a different rule is not detected. For example, CV-PY-006 is deleted, then a new, unrelated rule is typed in as CV-PY-006. It passes because 006 was already handed out (at or below the counter) | Phase 1 has no screen. Detecting it would mean comparing every rule against all old versions | Phase 9: the Admin screen will only hand out new IDs through `next_rule_id`, so a person can't type one in |
| P5 | The "database busy" error (`DatabaseBusyError` in `da_db.py`) is its own type, separate from rulebook errors (`RulebookError`). Code that catches only `RulebookError` misses a busy database | It is kept separate on purpose: any table can be busy, not just the rulebook. Phase 1 has no screen that needs to catch it | Phase 9: the Admin screen must catch both `RulebookError` and `DatabaseBusyError` |
