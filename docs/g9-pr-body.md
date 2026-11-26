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
- W26-6: clicking the Tests tab again after a Dispute. W26-7: F5. W26-8: waiting for the tab to settle.

### Known gaps
- Step 8 (no invented cases, T2/G9-9) waits for Gian: the planner runs after Understand is confirmed.
- No browser test for the Tests tab scroll (G9-15) or the Admin -> Start a change request flow (G9-17);
  both are covered by callback and wiring tests. Worth one manual check at 1366 px.
