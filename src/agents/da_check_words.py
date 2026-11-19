"""The words of a check run (Check my edits), in one place (Phase 8 fix 1, F6 and F9).

A check run is a build run of kind `check`. Inside the system its status stays BUILDING (no new
status); only the screen says "testing". The build screens and the Refine screens both read these
lines, and Phase 9 can reuse them. Plain text only: nothing here decides anything.
"""

CHECK_KIND = "check"
CHECK_PILL = "TESTING"
CHECK_CHAT_LINE = "Testing your edits. This takes a few minutes. You can leave this page."
# Fix B2 (S6): the automatic check after "Add this test" says so before it runs.
NEW_TEST_CHECK_LINE = "Checking your new test against the current code..."
CHECK_BANNER = "One test pass on your files (the AI changes nothing)."
CHECK_CANCEL_LABEL = "Cancel test"
CHECK_BOX_TITLE = "This test run"
# Fix B1 (F3, F5): words for a failure that is the Developer Assistant's own (batch B2 reuses them).
NOT_PROVEN_TEXT = (
    "Some tests did not report a result. This is a problem in the Developer Assistant, "
    "not in your code. Run the tests again, or Get help."
)
SYSTEM_HELP_LINE = "This looks like a problem in the Developer Assistant, not your code."
SEND_TO_SENIOR_LABEL = "Send to my senior"
# Fix NP (N2): a test file that cannot load. The first two end a build like Not proven does.
MISSING_LIBRARY_TEXT = (
    "The server's Python is missing `{module}`. "
    "This needs the CodeVision team, not a code change."
)
FROZEN_TEST_TEXT = "A frozen test cannot run: {message}"
SYSTEM_FAILURE_MESSAGES = (NOT_PROVEN_TEXT,)  # the paused-build messages that are the DA's fault
_SYSTEM_PREFIXES = ("The server's Python is missing ", "A frozen test cannot run: ")


def is_system_message(message: str) -> bool:
    """True for a paused-build message that is the Developer Assistant's fault (F3 and NP)."""
    return message in SYSTEM_FAILURE_MESSAGES or message.startswith(_SYSTEM_PREFIXES)


def check_version_name(build_number: int) -> str:
    """The Versions row name of a check run."""
    return f"Test run {build_number} (your edits)"


def testing_files_line(planned: int, edited: int) -> str:
    """The progress line at the start of a check run. `edited` counts only files whose text
    differs from the last one written; 0 means the run is for his new test case."""
    if edited == 0:
        return f"Testing {planned} planned file(s) with your new test"
    return f"Testing {planned} planned file(s) ({edited} edited by you)"
