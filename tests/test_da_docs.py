"""The two work-test documents (Phase 6 fixes, section 8: F9d, O6). They are instructions for the
work laptop, where only Command Prompt and the app itself can be used."""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
WORKSPACE = (DOCS / "workspace-work-test.md").read_text(encoding="utf-8")
BUILD = (DOCS / "build-work-test.md").read_text(encoding="utf-8")
ECHO = r"echo def validate(path): return True> C:\Dev\practice\src\agents\upload_validator.py"
TYPE = r"type C:\Dev\practice\src\agents\upload_validator.py"


def code_blocks(text: str) -> list[str]:
    return re.findall(r"```\n(.*?)```", text, flags=re.DOTALL)


def test_the_workspace_doc_has_the_one_line_that_creates_the_file():
    blocks = "\n".join(code_blocks(WORKSPACE))
    assert blocks.count(ECHO) >= 1
    # Exactly one line in the first (setup) block creates the file.
    setup = code_blocks(WORKSPACE)[0]
    lines = setup.splitlines()
    creating = [line for line in lines if "echo" in line and "upload_validator" in line]
    assert creating == [ECHO]


def test_the_workspace_doc_shows_the_content_with_type_and_what_it_must_print():
    setup = code_blocks(WORKSPACE)[0]
    assert TYPE in setup.splitlines()
    assert setup.splitlines().index(TYPE) > setup.splitlines().index(ECHO)
    assert "must print exactly this one line" in WORKSPACE
    assert "```\ndef validate(path): return True\n```" in WORKSPACE


def test_the_workspace_doc_warns_that_a_build_writes_into_the_practice_folder():
    assert "a build writes into this practice folder" in WORKSPACE
    assert r"del C:\Dev\practice\src\agents\excel_processor.py" in WORKSPACE
    # ... and tells how to put the file back.
    after_warning = WORKSPACE.split("a build writes into this practice folder")[1]
    assert ECHO in after_warning


def test_the_workspace_doc_has_no_rescan_button_step_any_more():
    assert "press **Re-scan**" not in WORKSPACE
    assert "no separate **Re-scan** button" in WORKSPACE


def test_the_build_doc_says_what_the_fake_and_the_onprem_build_need():
    assert "FAKE build" in BUILD and "you do NOT set `DA_SANDBOX_SOURCE_DIR`" in BUILD
    assert "ONPREM build" in BUILD and "you MUST set `DA_SANDBOX_SOURCE_DIR`" in BUILD
    assert "that CONTAINS `src`" in BUILD
    assert r"C:\Users\<you>\Desktop\codevision" in BUILD
    assert "restart the app" in BUILD.lower() and "Resume build" in BUILD


def test_the_build_doc_uses_the_new_button_names_and_warns_about_reusing_the_folder():
    assert "Try again" not in BUILD and "Stop build" not in BUILD
    assert "Cancel build" in BUILD and "Audit tab" in BUILD
    assert "A build writes into the practice folder" in BUILD
    assert r"src\agents\excel_processor.py" in BUILD


def test_every_command_in_the_documents_is_a_command_prompt_command():
    for name, text in (("workspace", WORKSPACE), ("build", BUILD)):
        commands = "\n".join(code_blocks(text))
        for powershell_only in ("$env:", "Get-", "Set-", "Invoke-", "Remove-Item", "New-Item"):
            assert powershell_only not in commands, (name, powershell_only)
        # DevTools: no step may ask for it. (The text only says it is blocked.)
        assert "F12" not in text and "Ctrl+Shift+I" not in text
        assert "Command Prompt" in text
