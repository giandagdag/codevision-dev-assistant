# Parked items

Small items found in the Phase 0, 1 and 2 work and deliberately left for later. None of them blocks the current phase.

| # | Item | Why it is parked | When to fix |
|---|---|---|---|
| P1 | Table setup runs on every database call (`executescript` in `db_tbl_da_requests.py`, `db_tbl_da_audit.py`, and, since Phase 1, `db_tbl_da_rulebook.py`) | It works and costs little on SQLite, and this code changes anyway when we move to CodeVision's database | Before the code is copied into CodeVision, as part of the database switch (Q2) |
| P2 | Swap `da_logging.py` for CodeVision's shared logger | We don't yet know whether CodeVision has one (spec question Q4) | Once Q4 is answered, before the move to CodeVision |
| P3 | ~~Audit details that refer back to themselves raise a raw `ValueError` instead of our plain message~~ **Fixed in Phase 2A** (`insert_audit_event` in `db_tbl_da_audit.py`) | - | - |
| P4 | A retired rule ID re-typed by hand for a different rule is not detected. For example, CV-PY-006 is deleted, then a new, unrelated rule is typed in as CV-PY-006. It passes because 006 was already handed out (at or below the counter) | Phase 1 has no screen. Detecting it would mean comparing every rule against all old versions | Phase 9: the Admin screen will only hand out new IDs through `next_rule_id`, so a person can't type one in |
| P5 | The "database busy" error (`DatabaseBusyError` in `da_db.py`) is its own type, separate from rulebook errors (`RulebookError`). Code that catches only `RulebookError` misses a busy database | It is kept separate on purpose: any table can be busy, not just the rulebook. Phase 1 has no screen that needs to catch it | Phase 9: the Admin screen must catch both `RulebookError` and `DatabaseBusyError` |
| P6 | Discarding a draft request | Decided in the Phase 2 spec (D-E) to keep Phase 2 small. Unfinished drafts stay in "My recent requests" | After Phase 2, if the list gets cluttered |
| P7 | Skipping ahead when one answer covers several questions | Decided in the Phase 2 spec (D-G): questions are always asked in order, which is simpler and predictable | After Phase 2, once real answers show it is needed |
| P8 | Fill the `onprem` provider (Qwen and Llama) using CodeVision's `tools/spirare.py` `API_CALL`, with certificate checking on | Needs photos of `API_CALL` and the chat part of `payload_generation.py` (Q1) | Before the first test at work |
| P9 | The secret check (rule R8) is a short fixed list of patterns. It can refuse an ordinary sentence such as "password: the user types it twice", and it will miss a secret in an unusual format | The spec asks for a short fixed list; the message says why it was refused, so the developer can rephrase | After Phase 2B, once real answers show how often it happens |
