## Fix G9: the requirement is the referee and follows the rulebook

Spec `specs/fix-g-9.md`, plan `specs/fix-g-9-plan.md`.

### What changed
- **Understand:** the record is checked against the rulebook (plain code plus one AI call). Conflicts
  block Confirm. Buttons: Use the suggested wording, Change it myself, Ask for an exception (a senior
  approves or rejects it; approved ones become RX-n lines that flow to Approach, Build and the Tester).
- **Tests come only from the requirement:** the test writer sees the criteria word for word; expected
  text must come from the requirement before tests freeze; a repeated failure asks the referee once.
- **Builder:** required results (given -> output) are listed in its prompt and run in the sandbox
  before the Tester.
- **Findings:** "the code complies" findings are dropped; DD/RU/RX/rule cites show their meaning on
  hover and focus; the Check column shows the check's name.
- **Screens:** hint lines under Re-scan and Check my folder; Missing backup chip at the right end;
  See the findings is a button that scrolls every press; a redraw keeps the user's tab until the step
  changes; "Opening..." only on the Developer Assistant page; other pages own the address.

### Workarounds that end with this merge
- W26-1: escalation answer as the way out of a wrong test (T-4), and wording every failure case by hand.
- W26-7: F5 (the Admin tab address is tested with a real F5 on a non-default tab).

### Closed by the G9 finish steps (F1 to F8)
- B3 (required results for command-line pairs) is built (F3); not parked any more.
- The v2 and later refine lane has the same gate with the wording, change and exception buttons (F5).
- A `ZONE:` conflict is shown as a rule conflict (F6).
- G9-15 (See the findings pressed three times) and G9-16 (tab kept after a Dispute) have Playwright
  tests (`tests/test_da_g9_finish_browser.py`); the Inbox buttons have one too (F8). W26-6 is closed.
- Step 8 (no invented cases): Gian answered; F1 checks gaps at Understand.
- W26-8 (Admin tab clicks reload the whole page): **fixed in G9 finish F4**. A tab click writes
  the address with `history.replaceState` (no reload, no history entry) and keeps the tab in a
  store; F5 and a typed `?tab=` still read the address. The old "stuck on Opening..." after Admin,
  Home, Start was a different cause: the Address-to-Tabs callback ran on every address change while
  the Admin tabs were gone. It is removed (Playwright tests cover Admin, tab, Home, Start).
  Back/Forward no longer step through tabs (a click replaces the address).

### Known gaps (open, none Critical or High)
- Inbox Approve/Reject on an exception ask closes the whole row, even if it also holds another
  reason (for example Get help).
- T3 does not check lower-case one-word expected values; contract names are not counted as
  requirement text.
- The audit keeps the AI's gap wording (`gap.case`); it should keep the number only.
- A case dropped by T3 only gets an FYI line on the checklist, not a Summary-tab question (F1 asks
  at Understand).
- The G9-18 browser test clicks 2 Admin tabs, not every tab.

### Test results (commit e4014d6)
pytest, all groups pass: ops and a-f, g-l 442, m-r 476, s-z 1184, test_db 120. ruff clean.
Smoke check passed.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
