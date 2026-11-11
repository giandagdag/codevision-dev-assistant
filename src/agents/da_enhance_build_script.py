"""Scripted Build replies for an Enhance request on the made-up limits program (Phase 9, step 14c).

The fake provider and the pretend work server use these so a whole enhance build can run with no
AI: the contract, the criterion tests and the edit blocks for `limits_expiry_report.py`. The text
comes from the "enhance" part of `da_build_fake_script.json`.

Test-only switches (set in `da_build_agent.FAKE_SWITCHES`, never by the app):
  edit_outside_scope  the edit block changes `format_expiry` (A8 when it is not in scope)
  signature_change    the edit block adds an argument to `days_left` (A9 when a file outside the
                      plan calls it)
"""

import json
import re

KIND_LINE = re.compile(r'"kind": "(enhance|fix)"')


def is_enhance_build_prompt(prompt: str, script: dict) -> bool:
    """True for a Build prompt of an enhance or fix request that plans the made-up target."""
    section = script.get("enhance")
    return bool(section) and bool(KIND_LINE.search(prompt)) and section["path"] in prompt


def scripted_contract(script: dict) -> str:
    return json.dumps(script["enhance"]["contract"])


def criterion_test_parts(script: dict) -> tuple[list[str], tuple[str, ...]]:
    """(the import lines of the criterion test file, the check bodies used in turn per case)."""
    section = script["enhance"]
    return list(section["test_imports"]), tuple(section["test_checks"])


def scripted_code(prompt: str, script: dict, switches: frozenset[str], present_prefix) -> str:
    """Edit blocks for the target. A fix round, or a text the first edit already changed, gets a
    harmless block that matches text still there (so Layer A has nothing to flag)."""
    section = script["enhance"]["edits"]
    # A switch sends its bad edit every round, so the check it tests keeps failing.
    for switch in ("edit_outside_scope", "signature_change"):
        if switch in switches:
            edit = section[switch]
            return f"<<<<<<< FIND\n{edit['find']}\n=======\n{edit['replace']}\n>>>>>>> REPLACE\n"
    find, replace = section["first"]["find"], section["first"]["replace"]
    if "## Why the last round failed" in prompt or find not in prompt:
        find = replace = present_prefix(prompt, replace)
    return f"<<<<<<< FIND\n{find}\n=======\n{replace}\n>>>>>>> REPLACE\n"
