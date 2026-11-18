# Fix batch B2: screens and flow from Gian's work testing (14 Nov list)

Version 1.0 APPROVED, 17 Nov 2026 (20:40 SGT). Written in the project chat from
`claude/findings-2026-11-14-decisions.md` sections B and C (agreed item by item on 14 Nov, the
source of truth: do not re-open them unless the code proves one wrong). Gian, 17 Nov 20:26: "go
ahead with your recommendations, I give you full authority": every D-x below is option 1.
D1 (test report) is its own spec (`specs/fix-d1-test-report.md`), built before this one.

Branch `phase-b2-screens`, cut from `auto/phases-7-10` after D1 and Phase 11 fix 3 are merged (merge
the newest `auto/phases-7-10` in before planning). PR into `auto/phases-7-10`; the chief merges it.
Plan, plan review, small steps with tests, code review (max 3 rounds), full pytest, ruff, smoke
check. Commit subjects say "B2 step N" so the board can count. Laptop team, no spec-writer run.

## 0. Why

These 9 items were agreed on 14 Nov but only batch B1 (trust fixes) was built. Checked on 17 Nov
(`auto/phases-7-10`): none of the items below is in the code.

## 1. What we build

| # | Item | Today (checked 17 Nov) | Build |
|---|---|---|---|
| S1 | **3** Lane labels | `agents/da_refine_lanes.py` lines 88 to 90: "Requirement change", "Approach change", "Bug" | **"Change what it does"** (requirement), **"Change how it's built"** (approach), **"It's not working as agreed"** (bug). Words in one place (constants); chat lines, Audit and Handoff use the same words. Internal lane keys unchanged |
| S2 | **4** Cancel button | `CANCEL_LABEL` buttons drawn like the lane buttons | Plain grey outline button, set apart from the three lanes (own row or a divider), same on every step that offers Cancel |
| S3 | **6** Explain simply / Help me decide | Not there | Two buttons at lane choice and in Get help. **Explain simply:** one AI call, the current choice explained at high-school level (no jargon, max 120 words), shown in chat. **Help me decide:** one AI call that recommends one lane with a one-line reason; the recommended button gets a small "Suggested" tag; **he still clicks**. If he is still unsure, Get help offers Send to my senior as today. Both calls are audited; a failed AI call says so and changes nothing |
| S4 | **7** Bug lane | Text box "Describe the bug" exists | Keep the text box first. Above it a button **"Let the AI describe it"**: one AI call drafts the description from the failing tests and the last chat lines, puts it **in the box** for him to edit, never sends it by itself |
| S5 | **8** Lock buttons while waiting | Not locked everywhere | While a request waits on the AI, every action button on the page is disabled (greyed, not hidden). Exceptions that stay active: **Cancel build**, **Cancel test**, **Home**. A second click can never start a second AI call (server check too, not only the screen) |
| S6 | **10** Announce the automatic check | Runs silently after "Add this test" | Chat line before it runs: "Checking your new test against the current code..." and one after with the result. Behaviour unchanged |
| S7 | **16** Decision limit and assumptions | `DEFAULT_MAX_MATERIAL_DECISIONS = 5` (`pydantic_classes/da_rulebook_models.py`); the work seed `da_rulebook_seed_work.json` has no `max_material_decisions`, so **work runs with 5**; at the limit the request stops for a senior | (a) Default 8 in the model and in both seeds (Admin can still change it, 1 to 15). (b) The AI asks open decisions **in batches** (up to 3 per message) instead of one by one. (c) At the limit, two buttons: **"Proceed with these assumptions"** and **"Send to my senior"** (senior inbox, not Admin). (d) Proceed: the AI writes one assumption per open decision into a new **Assumptions** section of the Summary; he reviews and edits them at the checkpoint; on Confirm they become part of the requirement (criteria) and are tested. (e) Never assumed: anything about **security, money amounts or customer data**; those stay as decisions and only the senior can answer them. (f) A senior can reopen the request with more rounds (sets a higher limit for this request only, audited) |
| S8 | **2** No negative scenario applies | `da_understand_checks.py` line 188: "At least 1 negative scenario is needed." always | Keep the rule as the default. New option **"No negative scenario applies"** with a required one-line reason (max 200 characters). The AI suggests it when the request has no inputs. The reason is saved in Audit and shown at Handoff (PR summary). The Tester and code tests still run as normal |
| S9 | **1 + D2** Full-width layout | Fixed width; Home cards different heights | Page uses the full width on large monitors; the 3 Home cards are equal height; extra width goes to the right panel; chat lines keep a readable width (max about 80 characters per line). Check at 1366 px and 1920 px |

## 2. Edge rules

- No new library, no new status. S7 adds fields (Assumptions, per-request limit) with a database
  change done the same way as earlier phases (new columns with defaults, old rows still read).
- S3, S4 and S7(d) are AI calls: fake AI scripts for each in demo mode, and they use the role models
  from Admin. A failed call never moves the request.
- S7 never assumes a security, money or customer-data decision, even if he presses Proceed.
- Words for every label and chat line come from constants, so a later wording change is one edit.

## 3. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| B2-1 | Given the Refine bar, when drawn, then the lanes read "Change what it does", "Change how it's built", "It's not working as agreed", and Audit uses the same words |
| B2-2 | Given any step with Cancel, when drawn, then Cancel is an outline grey button outside the lane row |
| B2-3 | Given lane choice, when Explain simply is pressed (fake AI), then the chat shows the explanation and nothing else changes |
| B2-4 | Given lane choice, when Help me decide is pressed, then one button is tagged "Suggested" with a one-line reason and no lane starts until he clicks |
| B2-5 | Given the bug lane, when Let the AI describe it is pressed, then the box holds the draft and nothing is sent |
| B2-6 | Given a request waiting on the AI, when the page is drawn, then every action button is disabled except Cancel build, Cancel test and Home; a forced second call is refused by the server |
| B2-7 | Given Add this test, when the check runs, then the chat says it is checking before and the result after |
| B2-8 | Given a new rulebook or the work seed, when loaded, then the decision limit is 8 |
| B2-9 | Given 5 open decisions, when the AI asks, then they come in batches of at most 3 |
| B2-10 | Given the limit is reached, when Proceed with these assumptions is pressed, then the Summary has an Assumptions section, he can edit it at the checkpoint, and after Confirm each assumption is a criterion with tests |
| B2-11 | Given an open decision about customer data, when Proceed is pressed, then it is not assumed and stays for the senior |
| B2-12 | Given Send to my senior at the limit, when pressed, then an item is in the senior inbox; when the senior reopens with 3 more rounds, the request continues with a limit of 11 for that request only |
| B2-13 | Given a request with no inputs, when the negative scenario step comes, then the AI suggests No negative scenario applies; with a reason the gate passes; without a reason it does not |
| B2-14 | Given that reason, when Handoff runs, then the PR summary and Audit show it |
| B2-15 | Given a 1920 px window, when Home is drawn, then the cards have equal height and the page uses the full width; chat lines stay readable (layout test on the component tree; visual check by Gian) |

## 4. Choices (D-x), all option 1 (Gian gave full authority, 17 Nov 20:26)

- **D-A Batch size for decisions:** 1. Up to 3 per message. 2. All at once.
- **D-B Explain simply and Help me decide:** 1. Buttons at lane choice and Get help only. 2. Everywhere.
- **D-C Senior reopen:** 1. Senior picks 1 to 5 more rounds. 2. Fixed 3 more.

## 5. Out of scope

- D1 (own spec). Director item D4 (rule versioning and rollback, parked). "Review my code" (on hold).
- Coverage measuring (needs a new library).
