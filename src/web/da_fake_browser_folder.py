"""A pretend developer folder that answers like the browser script does (plan decision P9).

The real browser reads and writes the developer's laptop with JavaScript (da_workspace.js). The
tests and the smoke check have no laptop, so this class plays the same part in plain Python: it
reports FACTS about a folder and runs a WRITE JOB with the same edit guard. It keeps files in a
dictionary, like a source library held in memory instead of on disk.
"""

from agents.da_workspace_checks import (
    edit_guard_allows,
    fingerprint,
    path_problem,
)
from pydantic_classes.da_workspace_models import (
    ABSENT,
    FileFact,
    FolderFacts,
    WriteJob,
    WriteReport,
    WriteStop,
    WrittenFile,
)


class FakeBrowserFolder:
    def __init__(
        self,
        name: str = "codevision",
        files: dict[str, str] | None = None,
        folders: set[str] | None = None,
        git: bool = True,
    ):
        self.name = name
        self.files: dict[str, str] = dict(files or {})
        self.extra_folders = set(folders or set())
        self.git = git
        # Every path the pretend browser opened to read, so a test can prove what was NOT read.
        self.reads: list[str] = []

    # --- the developer working in the folder ---

    def edit(self, path: str, text: str) -> None:
        self.files[path] = text

    def folder_exists(self, folder: str) -> bool:
        if folder in self.extra_folders:
            return True
        prefix = folder.rstrip("/") + "/"
        return any(path.startswith(prefix) for path in self.files)

    # --- the facts (what the browser collects, spec section 4) ---

    def facts(
        self, planned_paths: list[str], markers: list[str], request_id: str, max_kb: int = 512
    ) -> FolderFacts:
        marker_state = {marker: self.folder_exists(marker) for marker in markers}
        stripped = [m.removeprefix("src/") for m in markers]
        looks_like_src = bool(markers) and all(self.folder_exists(m) for m in stripped)
        return FolderFacts(
            folder_name=self.name,
            markers=marker_state,
            looks_like_src=looks_like_src and not any(marker_state.values()),
            has_git=self.git,
            files=[self._file_fact(path, max_kb) for path in planned_paths],
        )

    def _file_fact(self, path: str, max_kb: int) -> FileFact:
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        parent_exists = not parent or self.folder_exists(parent)
        if path not in self.files:
            return FileFact(path=path, exists=False, parent_exists=parent_exists)
        self.reads.append(path)
        text = self.files[path]
        if len(text.encode("utf-8")) > max_kb * 1024:
            return FileFact(path=path, exists=True, parent_exists=True, too_big=True)
        return FileFact(
            path=path, exists=True, parent_exists=True, text=text, fingerprint=fingerprint(text)
        )

    # --- the write job (spec section 5) ---

    def run_job(self, job: WriteJob) -> WriteReport:
        allowed = {item.path for item in job.files}
        written: list[WrittenFile] = []
        for item in job.files:
            reason = self._refusal(item.path, item.expected, allowed)
            if reason:
                stop = WriteStop(path=item.path, reason=reason)
                return WriteReport(written=written, stopped=stop)
            self.files[item.path] = item.text
            back = self.files[item.path]
            written.append(WrittenFile(path=item.path, text=back, fingerprint=fingerprint(back)))
        return WriteReport(written=written)

    def _refusal(self, path: str, expected: str, allowed: set[str]) -> str:
        if path not in allowed or path_problem(path):
            return f"{path} is not allowed."
        if not edit_guard_allows(self.files.get(path), expected):
            what = "already exists" if expected == ABSENT else "changed since last time"
            return f"{path} {what}. Re-scan first."
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent and not self.folder_exists(parent):
            return f"The folder {parent} does not exist, and the app does not create it."
        return ""
