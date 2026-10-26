# Phase 1: Rulebook core

Status: APPROVED v1.0 (25 Oct 2026)
Depends on: Phase 0
Next phase: Phase 2, Understand

## In plain words

The rulebook is the one set of house rules that both the generator (Qwen) and the
Independent Reviewer will read in later phases. This phase builds the rulebook's storage:
save a new version, see every version, restore an old one, and lock each request to the
version it started under. No screens yet (the Admin console is Phase 9).

AS400 comparison: like saving every change to a source file as a brand-new member (RULEBK001,
RULEBK002, ...) instead of overwriting one member. Old members are never changed or deleted, and a
running job keeps reading the member it opened when it started.

## 1. Goal

- Store the rulebook as numbered versions (v1, v2, v3...). Every save creates a new version.
- Old versions can never be edited or deleted.
- Restore copies an old version into a new one. Nothing is lost.
- Each new request is pinned to the active version and keeps it until it finishes.

## 2. In scope

### 2.1 Rulebook contents (only 3 areas for now)
The rulebook grows one area at a time, in the phase that first needs it.
Phase 1 includes:

**A. Charter** (used by the Readiness Gate in Phase 4)
- 5 sections: Purpose, Scope (in-scope list and out-of-scope list), Architecture principles,
  Constraints, Glossary (term and meaning)
- A size check: charter length as a % of a 6,000-character limit (about 2 pages).
  Status is green under 80%, amber 80% to 100%, red over 100%. A red charter can still be saved,
  but the check reports it.

**B. Rules** (used by generation and review in Phases 5 and 6)
- Two kinds: `judgement` (coding rules only an LLM can check) and `ui_convention`
- Each rule has: rule ID, title, kind, tags (for example `data`, `logging`, `ui`, `general`),
  severity (`must_fix`, `should_fix`, `fyi`), why it matters, a good example, a bad example,
  and a source (for example "Written by Admin")
- Rule IDs are generated automatically: `CV-PY-001` for judgement rules, `CV-UI-001` for
  UI conventions. A number is never reused, even after its rule is deleted.
- At most 10 judgement rules (pilot cap)

**C. Generation and review policy** (used in Phases 5 and 6)
- Default level and max level, each one of `L0`, `L1`, `L2`, `L3`
- Never-generate zones: name, description, examples (for example Security, Login)
- Max review rounds: a whole number from 1 to 5
- Escalation triggers: a fixed list of exactly 3, each on or off:
  1. max rounds reached with a Must fix still open
  2. request is out of scope
  3. developer disputes a finding

### 2.2 Versions
Each version stores:
- version number, a full copy of the rulebook, a change note, who saved it (a user ID),
  when (UTC), and "restored from" (empty unless it came from a restore)
- The active version is always the newest one.

### 2.3 Functions
- `publish_first_version(rulebook, saved_by, note)`: creates v1. Refused if any version exists.
- `save_new_version(rulebook, base_version, saved_by, note)`: creates the next version.
- `get_active_version()`, `get_version(number)`, `list_versions()` (newest first)
- `restore_version(number, saved_by, note=None)`: copies that version into a new version
- `next_rule_id(kind)`: returns the next unused ID for that kind
- `get_rulebook_for_request(request_id)`: returns the version the request is pinned to

### 2.4 Pinning
- When a request is created, its rulebook version is set to the active version.
- If no rulebook has been published yet, creating a request is refused with a plain message.
- The pinned version never changes, even after newer versions are saved or restored.

### 2.5 Starter rulebook
- `src/data/da_rulebook_seed.json`: a made-up v1 with a short charter, 5 judgement rules,
  2 UI conventions, Default L2, Max L2, zones Security and Login, 3 review rounds, all 3 triggers on.

### 2.6 Smoke check (extend `da_smoke_check.py`)
After the Phase 0 items, it also prints:
1. v1 published from the seed file
2. a request created and pinned to v1
3. v2 saved with one changed rule; the request is still pinned to v1
4. v1 restored as v3 ("Restored from v1"); all 3 versions listed, newest first

## 3. Out of scope (do NOT build in Phase 1)
- Any screen (Admin console is Phase 9)
- Capability catalog and named seniors (Phase 6)
- Repository and index settings (Phase 3)
- Brand constants, golden examples, SonarQube severity mapping (Phases 5 and 6)
- Choosing which rules to send to the LLM by tag (Phase 5)
- "What changed" comparison between versions (Phase 9)
- Health metrics, AI rule suggestions, "fires %" (Phase 9 or later)
- Who is allowed to edit the rulebook (bank access control handles this)

## 4. Rules
- R1. Versions are append-only. No function may edit or delete one, and the database refuses it
  (same trigger approach as the audit trail).
- R2. Every save needs a non-empty change note.
- R3. A save is refused, with nothing written, if the rulebook breaks any of these:
  default level is higher than max; L3 is used anywhere (locked for the pilot);
  more than 10 judgement rules; review rounds outside 1 to 5; a trigger list that is not exactly the 3 above;
  two rules sharing one ID. The message lists every problem found, in plain words.
- R4. Stale-save protection: `save_new_version` is refused if `base_version` is not the active
  version (someone else saved first). The message names the newer version.
- R5. Saving a rulebook identical to the active one is refused ("No changes to save").
- R6. Restoring the version that is already active is refused.
- R7. Rule ID numbers are never reused (use a counter, not "highest number plus one").
- R8. Made-up content only. No real names, rules, or text from UOB.
- R9. All Phase 0 rules still apply (no secrets, tests never call real AI, plain errors,
  Python 3.14, no new libraries).

## 5. Done when
- [ ] `pytest` passes with 0 failures (Phase 0 tests included)
- [ ] `ruff check` reports 0 problems
- [ ] The smoke check prints all Phase 0 items and the 4 new items in section 2.6
- [ ] Tests prove: a version cannot be edited or deleted, even with raw SQL
- [ ] Tests prove: a pinned request still gets v1 after v2 and v3 exist
- [ ] Tests prove each refusal in R2 to R6, with a plain message
- [ ] Tests prove: after rule `CV-PY-006` is deleted, the next judgement rule is `CV-PY-007`, not 006
- [ ] Tests prove: the charter size check returns the right status at 79%, 80%, 100%, and 101%
- [ ] Creating a request with no rulebook published gives a plain message
- [ ] The independent reviewer reports 0 Must fix findings
- [ ] README gets a short plain-language "How Phase 1 works" section
- [ ] `specs/parked-items.md` is updated if anything is deferred

## 6. Open questions (do not block Phase 1)
- Q5. Real Admin user IDs will come from CodeVision's login. Until then, `saved_by` is a plain text ID.

## 7. Decisions made during planning (25 Oct 2026)
- D1. The smoke check uses a fresh temporary database for every run, deleted afterwards.
  It never writes rulebook versions to the real database (`DA_DB_PATH`).
- D2. Charter length = the characters of all text the Admin wrote (purpose, each scope item,
  principles, constraints, glossary terms and meanings). Storage punctuation such as JSON
  brackets, quotes and field names does not count.
