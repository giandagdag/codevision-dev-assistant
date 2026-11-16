# Phase 11 fix 2: code review findings

## Round 1 (3 Must fix, 9 Should fix, 6 Nice to have)

Checks seen by reviewer: ruff clean, smoke check passed (steps 1 to 40), many pytest subsets passed. Full suite not finished by the reviewer (about 40 minutes).

### Must fix
1. `tests/test_da_admin_screens_browser.py:49-60,85-106`: AG-16 not met. The `live` fixture writes no `da_module_tags.json`, so the queue picture has no AI cards and the meaning search shows unrelated hits. Fix: run `run_tagging(...)` with `ScriptedTaggerClient()` into tmp_path first; search "creates markdown".
2. `src/agents/da_admin_overview.py:273-282`: `server_settings_view` has no SonarQube rows (URL, profile, language, token set / not set, never the value). Add a test that the token never shows.
3. `src/agents/da_sonar_client.py:39,45,75`: non-JSON reply (HTML login page), missing `profiles` or `key` crash the button. Catch ValueError, KeyError, TypeError and raise `SonarError("SonarQube did not answer")`. Test with an HTML reply.

### Should fix
4. `da_admin_tagger.py:146,163-167`: decisions made during a scan are overwritten. Re-read the file before saving and merge only the new entries.
5. `da_admin_rebuild.py:22,63`: `LOCK_MAX_AGE` (2 h) also applies to the scan lock. Give the tagger lock its own longer limit or refresh the lock after each module.
6. `da_admin_tagger.py:113-130,147`, `da_admin_tagger_job.py:84-85`: "wait for the next scan" is wrong for Scan all; limit applied before `is_sendable`. Filter first, then put untagged first.
7. `da_admin_scan_controls.py:15-18,25`: confirm text differs from spec 3.3 ("About N programs", "you can leave the page"; remove "Takes a few minutes"; button "Scan all programs").
8. `da_admin_catalog_tab.py:92-96`: placeholder does not change with mode; no debounce.
9. `tests/test_da_admin_meaning.py:25-48`: AG-1 test does not use shipped files. Add a test with `FakeSearchIndex.from_file()` plus shipped script summaries.
10. `da_admin_page_callbacks.py:687`, `da_admin_page.py:589,592`: Refresh does not redraw the panel; panel reads `load_settings()` directly.
11. `da_admin_tag_cards.py:82,95`, callback `:391`: silent "Approved." when another capability already holds the path. Say which one.
12. `da_llm_client.py:336-338`: error names `DA_CLAUDE_TAGGER_MODEL`; should be `DA_CLAUDE_GENERATOR_MODEL`.

### Nice to have
13. Result click filters by file-name text (Unassigned gives empty table).
14. Sonar snapshot written directly; use temp-then-replace.
15. Rejected programs return as proposals on every Scan all.
16. "The scan failed: {error}" shows raw text.
17. No callback-level test for `_ai_action`.
18. Spacing nits.
