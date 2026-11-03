"""Data shapes for the Workspace (Phase 5): what the browser reports, what the server decides,
and what is saved.

The browser only collects facts (does this file exist, what does it say). The server turns facts
into blockers, write jobs and re-scan results with plain code, so the rules can be tested with
made-up facts and no browser. Think of the facts as a DSPFD listing of the developer's library,
sent to the program that holds the change form.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_models import REQUEST_ID_PATTERN, Request
from pydantic_classes.da_request_record_models import ChatMessage

# Where the workspace is. "start" is not stored: it means no state row yet. ws_picking and
# ws_checking are shown by the browser only (plan decision P1), so they are not saved.
WorkspaceStep = Literal["start", "ws_blocked", "ws_ready", "ws_fallback", "escalated"]
WorkspaceMode = Literal["picker", "download"]
FileKind = Literal["baseline", "written", "scanned"]
LineEnding = Literal["\n", "\r\n"]
ScanOutcome = Literal["unchanged", "changed", "missing"]

# The word the edit guard uses for "this file must not exist yet".
ABSENT = "absent"

MAX_FOLDER_NAME = 255


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- facts, as the browser reports them ---


class FileFact(_Shape):
    """What the browser saw for one planned file."""

    path: str
    exists: bool
    parent_exists: bool
    # Only filled for an existing file that was small enough and valid UTF-8.
    text: str | None = None
    # The browser's own fingerprint. The server recomputes it and refuses a mismatch (P13).
    fingerprint: str | None = None
    too_big: bool = False
    not_utf8: bool = False


class FolderFacts(_Shape):
    """Everything the check needs to know about the picked folder (spec section 4)."""

    folder_name: str = Field(min_length=1, max_length=MAX_FOLDER_NAME)
    # Marker folder from the policy -> does it exist in the picked folder.
    markers: dict[str, bool] = Field(default_factory=dict)
    # True when the folder holds the markers one level up, minus "src/": the developer picked src.
    looks_like_src: bool = False
    has_git: bool = False
    files: list[FileFact] = Field(default_factory=list)


# --- the check result ---


class Blocker(_Shape):
    code: str  # B1 to B6
    text: str
    path: str = ""


class CheckResult(_Shape):
    """The outcome of the workspace check. Saved as JSON in the workspace state."""

    passed: bool
    blockers: list[Blocker] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Shown, never blocks. Phase 10 reads `has_git` to word the Handoff steps (Q10).
    info: list[str] = Field(default_factory=list)
    has_git: bool = False
    folder_name: str = ""


# --- the write job ---


class JobFile(_Shape):
    path: str
    text: str
    # The fingerprint the file must still have right now, or ABSENT for a new file.
    expected: str


class WriteJob(_Shape):
    """What the server hands the browser: only these paths may be written (rule W3)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    folder_name: str
    files: list[JobFile]


class WrittenFile(_Shape):
    """One file the browser wrote and read back."""

    path: str
    text: str  # the read-back text
    fingerprint: str  # the browser's hash of it (cross-checked by the server)


class WriteStop(_Shape):
    path: str
    reason: str


class WriteReport(_Shape):
    """What the browser sends back after running a job."""

    written: list[WrittenFile] = Field(default_factory=list)
    stopped: WriteStop | None = None


# --- re-scan ---


class ScanItem(_Shape):
    path: str
    outcome: ScanOutcome


class ScanResult(_Shape):
    items: list[ScanItem] = Field(default_factory=list)

    def count(self, outcome: ScanOutcome) -> int:
        return sum(1 for item in self.items if item.outcome == outcome)


# --- saved rows and state ---


class WorkspaceState(_Shape):
    """The working state of one request's workspace (a row in da_workspace_state)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    step: WorkspaceStep = "start"
    folder_name: str = ""
    mode: WorkspaceMode = "picker"
    last_check: CheckResult | None = None
    linked_at: AwareDatetime | None = None
    checked_at: AwareDatetime | None = None
    revision: int = Field(default=1, ge=1)


class WorkspaceFile(_Shape):
    """One saved version of a file's text (da_workspace_files, append-only)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    path: str
    file_version: int = Field(ge=1)
    kind: FileKind
    text: str
    fingerprint: str
    line_ending: LineEnding = "\n"
    mode: WorkspaceMode = "picker"
    approach_version: int = Field(default=0, ge=0)
    created_at: AwareDatetime | None = None


class FileRow(_Shape):
    """One line of the Build tab file table."""

    path: str
    action: Literal["create", "modify"]
    status: Literal["Not written yet", "Written", "Changed by you", "Missing", "Created"]
    baseline_at: AwareDatetime | None = None


class WorkspaceView(BaseModel):
    """Everything the screen needs to show the workspace for one request."""

    request: Request
    messages: list[ChatMessage]
    step: WorkspaceStep
    folder_name: str
    mode: WorkspaceMode
    check: CheckResult | None
    checked_at: AwareDatetime | None
    rows: list[FileRow]
    last_scan: ScanResult | None
    buttons: list[tuple[str, str]]
    # Browser-run buttons (picker, re-scan, download...) are listed apart from server buttons.
    browser_buttons: list[tuple[str, str]]
    note: str
    open_item: str
    revision: int
    # What the browser needs to run a job without asking the server first.
    planned_paths: list[str]
    markers: list[str]
    max_file_kb: int
    demo_mode: bool
