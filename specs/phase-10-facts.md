# Phase 10 facts (from Gian, project chat, 13 Nov 2026)

Facts for the Phase 10 spec writer. Format to copy: `specs/phase-11-admin-console.md`.
Source of truth: `specs/redesign-2026-10-31.md` sections 5.10 (Handoff) and 5.11 (Escalation).
Facts marked **work fact** are Gian's to decide: options, no recommendation, an issue each.

## Scope (Gian, 13 Nov 23:26)
- **Phase 10 tonight = Handoff + Escalations inbox only.**
- **"Review my code" (redesign 5.9) is NOT in this phase.** It is parked as **Phase 10b**, later.
  Do not build the third Home card's flow, its short Understand or "Let AI fix". The Home card may
  stay as it is today.
- Gian has a separate list of findings and enhancements (his own testing and his director's
  review). They come in their own thread after this phase. Do not guess them.

## What is already built (on `auto/phases-7-10`, Phases 7 to 9 and 11)
- Labels from the Tester (Phase 7): Ready for your review, Ready with warnings, Not passing,
  Unable to assess. Must fix / Should fix findings, Dispute on a Must fix.
- Refine and re-scan with fingerprints (Phase 8), edit protection, hand-edited files known.
- Enhance (Phase 9): catalog lookup, named senior per capability, the Unassigned queue, safety-net
  tests and gaps.
- Admin (Phase 11): the **five escalation triggers** (on/off) and **flag-for-review zones** are
  edited and saved in the rulebook; **capability catalog** has a named senior and a **backup
  senior**; Overview shows "No data yet (comes with Phase 10)" for handoffs and the four triggers
  other than Get help. Phase 10 must make those numbers real (read the existing metrics code).
- "Get help" already moves a request to `ESCALATION_REQUIRED`.

## Handoff (redesign 5.10), the rules Gian agreed on 31 Oct
- Allowed only at green or yellow (0 Must fix; each Should fix fixed or accepted with a reason)
  **and** a final fingerprint check shows the workspace equals what was last tested.
- The assistant never commits, pushes or approves. The developer commits from his clone (or ZIP
  copy) and opens the PR in Bitbucket himself.
- PR summary with a copy button: request ID, record version, one-line summary; criteria -> tests
  -> results; files changed and which ones were hand-edited; reuse and approach decisions;
  accepted risks with reasons; flag-for-review zones (the capability's named senior is a required
  reviewer); safety-net gaps; a capability still waiting in the Unassigned queue is marked.
- Status HANDED_OFF, request locked.

## Escalation (redesign 5.11)
- Five fixed triggers, plain code, each obeys its Admin on/off switch: (1) round cap hit twice in
  a row on the same request, (2) request or approach out of scope, (3) developer disputes a Must
  fix, (4) Tester "Unable to assess" twice, (5) Get help.
- Goes to the capability's named senior, or the backup senior.
- Senior inbox, inside the Developer Assistant: overrule a finding (audited), send guidance (goes
  into the chat and the next AI call), take over, close.
- Flag-for-review zones are **not** an escalation: they only make the senior a required PR
  reviewer.
- Idea parked on 6 Nov for Phase 10: **lock the developer's chat until the senior unlocks it**.
  Offer it as a ranked D-x (lock / no lock).

## Open items
- **Work fact:** how the work login names a user, so the inbox knows who is a senior (same open
  question as Phase 11 WF-2, issue #59). At home: a made-up ID list, like `DA_ADMIN_IDS`.
- **Work fact:** notification to the senior (email or Teams) is pending bank approval. Inbox only.
- **Work fact:** one shared database (Q2, issue #58): the inbox only works across laptops if
  developers and seniors use the same server database.

## Rules that still apply
Clean room (made-up names only), Dash Mantine Components, `da_` file names, tests never call a
real AI, Command Prompt only at work, "negative scenario" wording. Plain language, AS400
comparisons, ranked D-x options with one recommendation each, Given/When/Then, no em dashes.
Build it on ONE branch, `auto/phase-10` (the status board tracks phase `10`). If it is large,
order the plan steps so Handoff comes first and each run can stop cleanly; do not split branches.

## Decision (Gian, 14 Nov 10:2x SGT, project chat)
- The inbox stays **inside CodeVision only**: the `/inbox` page (D-G option 1). No email, no Teams,
  ever for this initiative (WF-2 answered: a, inbox only). Not a tab in the Admin console; seniors
  get no Admin rights.
- **Add an unread badge**: count on the Inbox menu entry plus a Home banner for seniors. Built in
  plan step 10b (tests 10-55, 10-56).
