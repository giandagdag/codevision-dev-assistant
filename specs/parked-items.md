# Parked items

Small items found in the Phase 0 reviews and deliberately left for later. None of them blocks Phase 0.

| # | Item | Why it is parked | When to fix |
|---|---|---|---|
| P1 | Table setup runs on every database call (`executescript` in `db_tbl_da_requests.py` and `db_tbl_da_audit.py`) | It works and costs little on SQLite, and this code changes anyway when we move to CodeVision's database | Before the code is copied into CodeVision, as part of the database switch (Q2) |
| P2 | Swap `da_logging.py` for CodeVision's shared logger | We don't yet know whether CodeVision has one (spec question Q4) | Once Q4 is answered, before the move to CodeVision |
| P3 | Audit details that refer back to themselves raise a raw `ValueError` instead of our plain message (`add_audit_event` in `db_tbl_da_audit.py`) | Very unlikely: our own code never builds such details | When a later phase starts passing richer details, or in any phase that touches the audit file |
