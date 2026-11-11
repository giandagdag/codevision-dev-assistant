"""The words of a check run (Check my edits), in one place (Phase 8 fix 1, F6 and F9).

A check run is a build run of kind `check`. Inside the system its status stays BUILDING (no new
status); only the screen says "testing". The build screens and the Refine screens both read these
lines, and Phase 9 can reuse them. Plain text only: nothing here decides anything.
"""

CHECK_KIND = "check"
CHECK_PILL = "TESTING"
CHECK_CHAT_LINE = "Testing your edits. This takes a few minutes. You can leave this page."
CHECK_BANNER = "One test pass on your files (the AI changes nothing)."
CHECK_CANCEL_LABEL = "Cancel test"
CHECK_BOX_TITLE = "This test run"


def check_version_name(build_number: int) -> str:
    """The Versions row name of a check run."""
    return f"Test run {build_number} (your edits)"


def testing_files_line(planned: int, edited: int) -> str:
    """The progress line at the start of a check run. `edited` counts only files whose text
    differs from the last one written; 0 means the run is for his new test case."""
    if edited == 0:
        return f"Testing {planned} planned file(s) with your new test"
    return f"Testing {planned} planned file(s) ({edited} edited by you)"
