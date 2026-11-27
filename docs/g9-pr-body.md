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
- G9-15 (See the findings pressed three times) has no browser test: a live Tests tab with findings
  needs a full build behind a real server. Only the button, the ids and the script wiring are tested.
  Please press it once by hand. G9-16 (tab kept after a Dispute) is tested on the drawn key only; the
  tab script itself runs in the browser and was not run in one.
- G9-17 and G9-18 have Playwright tests in `tests/test_da_admin_tab_address_browser.py`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
