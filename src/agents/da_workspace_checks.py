"""The Workspace rules as plain functions (spec sections 4, 5 and 6). No browser, no database.

The browser collects facts; these functions judge them. That keeps every rule testable with
made-up facts. A fingerprint here is like a member's last-changed stamp, but exact: if one
character changes, so does the code. The browser computes the same code with the same rules,
and the server always recomputes it from the text it receives (rule W3: never trust the browser).
"""

import hashlib
from collections.abc import Iterable

from agents.da_approach_checks import normalise_path
from pydantic_classes.da_approach_models import PlannedFile
from pydantic_classes.da_rulebook_models import Policy
from pydantic_classes.da_workspace_models import (
    ABSENT,
    Blocker,
    CheckResult,
    FileFact,
    FolderFacts,
    JobFile,
    LineEnding,
    ScanItem,
    ScanResult,
    WriteJob,
    WriteReport,
)

BYTE_ORDER_MARK = "﻿"

NOT_GIT_INFO = (
    "This folder is not a Git clone (for example a ZIP from Bitbucket). That is fine: at Handoff "
    "you upload the changed files to Bitbucket yourself, and the Handoff list tells you which "
    "ones."
)


class FactsProblem(ValueError):
    """The browser's facts or report do not add up. Nothing is saved; the message says why."""


# --- fingerprints and line endings (decision D-G) ---


def normalise(text: str) -> str:
    """Text as fingerprinted: no leading byte-order mark, and \\r\\n (or a lone \\r) as \\n."""
    if text.startswith(BYTE_ORDER_MARK):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def fingerprint(text: str) -> str:
    """SHA-256 of the normalised text as UTF-8: 64 characters, equal to the browser's."""
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def line_ending_of(text: str) -> LineEnding:
    """The style an existing file uses. A new file, or one with no line break, gets \\n."""
    return "\r\n" if "\r\n" in text else "\n"


def apply_line_ending(text: str, ending: LineEnding) -> str:
    """Write text in the given style (the app keeps an existing file's style)."""
    plain = normalise(text)
    return plain.replace("\n", "\r\n") if ending == "\r\n" else plain


# --- paths (rule W3, R1) ---


def path_problem(path: str) -> str:
    """Empty string if the path is safe; otherwise why not. Used on both sides of the job."""
    if not path or path != path.strip():
        return "The path is empty."
    if "\\" in path or path.startswith("/") or ":" in path:
        return f"{path}: only plain relative paths with / are allowed."
    for part in path.split("/"):
        if part in ("", ".", ".."):
            return f"{path}: '..', '.' and empty parts are not allowed."
    return ""


def parent_of(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


# --- the facts from the browser ---


def verify_facts(facts: FolderFacts, allowed_paths: Iterable[str]) -> None:
    """Refuse facts the server cannot trust (W3, P13): paths outside the plan, or a browser
    fingerprint that differs from the one computed here."""
    allowed = {normalise_path(path) for path in allowed_paths}
    for item in facts.files:
        if normalise_path(item.path) not in allowed:
            raise FactsProblem(f"The browser reported {item.path}, which is not in the file plan.")
        _verify_hash(item.path, item.text, item.fingerprint)


def _verify_hash(path: str, text: str | None, browser_hash: str | None) -> None:
    if text is not None and browser_hash is not None and fingerprint(text) != browser_hash:
        raise FactsProblem(
            f"The browser and the server disagree about {path}. Nothing was saved. Try again."
        )


def check_facts(
    facts: FolderFacts,
    files: list[PlannedFile],
    policy: Policy,
    remembered_folder: str = "",
) -> CheckResult:
    """The workspace check (spec section 4). Blockers B1 to B6, plus shown-only information.
    (B7, the tests-folder blocker, was dropped in Phase 6: tests never go to the workspace.)"""
    blockers: list[Blocker] = []
    warnings: list[str] = []
    if remembered_folder and remembered_folder != facts.folder_name:
        warnings.append(
            f"This request was linked to {remembered_folder}. You picked {facts.folder_name}."
        )
    folder_blockers = _folder_blockers(facts, policy)
    blockers.extend(folder_blockers)
    if not folder_blockers:
        blockers.extend(_file_blockers(facts, files, policy))
    info = [] if facts.has_git else [NOT_GIT_INFO]
    return CheckResult(
        passed=not blockers,
        blockers=blockers,
        warnings=warnings,
        info=info,
        has_git=facts.has_git,
        folder_name=facts.folder_name,
    )


def _folder_blockers(facts: FolderFacts, policy: Policy) -> list[Blocker]:
    if facts.looks_like_src:
        return [Blocker(code="B2", text="You picked the src folder. Pick the folder above it.")]
    missing = [marker for marker in policy.workspace_markers if not facts.markers.get(marker)]
    if not missing:
        return []
    wanted = " and ".join(policy.workspace_markers)
    return [
        Blocker(
            code="B1",
            text=(
                "This does not look like your CodeVision folder. "
                f"It should contain {wanted}."
            ),
        )
    ]


def _file_blockers(facts: FolderFacts, files: list[PlannedFile], policy: Policy) -> list[Blocker]:
    by_path = {normalise_path(item.path): item for item in facts.files}
    blockers: list[Blocker] = []
    for planned in files:
        path = normalise_path(planned.path)
        fact = by_path.get(path)
        if fact is None:
            raise FactsProblem(f"The browser did not report {path}.")
        blockers.extend(_one_file_blockers(path, planned.action, fact, policy))
    return blockers


def _one_file_blockers(path: str, action: str, fact: FileFact, policy: Policy) -> list[Blocker]:
    if action == "create":
        if fact.exists:
            return [
                Blocker(
                    code="B4",
                    path=path,
                    text=(
                        f"{path} already exists. Choose another folder, or change the approach "
                        "to modify it instead."
                    ),
                )
            ]
        if not fact.parent_exists:
            return [_missing_folder(path)]
        return []
    if not fact.exists:
        return [
            Blocker(
                code="B3",
                path=path,
                text=(
                    f"The plan changes {path}, but your folder does not have it. Pull the "
                    "latest code, choose another folder, or change the approach."
                ),
            )
        ]
    limit = policy.workspace_max_file_kb * 1024
    too_big = fact.too_big or (fact.text is not None and len(fact.text.encode("utf-8")) > limit)
    if too_big:
        return [
            Blocker(
                code="B6",
                path=path,
                text=(
                    f"{path} is larger than {policy.workspace_max_file_kb} KB, so it cannot "
                    "be read."
                ),
            )
        ]
    if fact.not_utf8 or fact.text is None:
        return [
            Blocker(
                code="B6",
                path=path,
                text=f"{path} is not a UTF-8 text file, so it cannot be read.",
            )
        ]
    return []


def _missing_folder(path: str) -> Blocker:
    return Blocker(
        code="B5",
        path=path,
        text=(
            f"The folder for {path} does not exist in your folder. The app never creates "
            "folders in src."
        ),
    )


# --- the write job (spec section 5) ---


def build_write_job(
    request_id: str,
    folder_name: str,
    items: list[tuple[str, str]],
    known: dict[str, tuple[str, LineEnding]],
) -> WriteJob:
    """One JobFile per (path, text). `known` maps a path to the (fingerprint, line ending) the
    file must have right now; a path that is not there is new and must be absent. A write job
    holds code files only: any path under tests/ is refused (Phase 6, tests stay in the app)."""
    job_files = []
    for path, text in items:
        problem = path_problem(path)
        if problem:
            raise FactsProblem(problem)
        if normalise_path(path).lower().startswith("tests/"):
            raise FactsProblem(f"{path}: tests are never written to your folder.")
        expected, ending = known.get(path, (ABSENT, "\n"))
        job_files.append(
            JobFile(path=path, text=apply_line_ending(text, ending), expected=expected)
        )
    return WriteJob(request_id=request_id, folder_name=folder_name, files=job_files)


def edit_guard_allows(current_text: str | None, expected: str) -> bool:
    """The edit guard (R5.1): may the file be overwritten? `current_text` is None when the file
    is not there. A new file expects ABSENT; an existing one must still have its fingerprint."""
    if expected == ABSENT:
        return current_text is None
    return current_text is not None and fingerprint(current_text) == expected


def verify_report(job: WriteJob, report: WriteReport) -> None:
    """Refuse a report that names a path outside the job, repeats one, or carries a hash that
    the server cannot reproduce (W3, P13)."""
    allowed = {item.path for item in job.files}
    sent = {item.path: fingerprint(item.text) for item in job.files}
    seen: set[str] = set()
    for item in report.written:
        if item.path not in allowed or item.path in seen or path_problem(item.path):
            raise FactsProblem(f"The browser reported {item.path}, which is not in the write job.")
        seen.add(item.path)
        if fingerprint(item.text) != item.fingerprint:
            raise FactsProblem(
                f"The browser and the server disagree about {item.path}. Nothing was saved."
            )
        # What was read back must be what was sent: otherwise the write went wrong.
        if item.fingerprint != sent[item.path]:
            raise FactsProblem(
                f"{item.path} was read back differently from what was written. Nothing was saved."
            )
    if report.stopped is not None and report.stopped.path not in allowed:
        raise FactsProblem(
            f"The browser stopped at {report.stopped.path}, which is not in the job."
        )
    # The browser writes in job order, so the written list must be a prefix of the job.
    order = [item.path for item in job.files]
    if [item.path for item in report.written] != order[: len(report.written)]:
        raise FactsProblem("The browser wrote the files in a different order than the job.")


def stop_message(job: WriteJob, report: WriteReport) -> str:
    """Plain words for a stopped job: which files are written, which are not (spec section 5)."""
    done = [item.path for item in report.written]
    left = [item.path for item in job.files if item.path not in done]
    stop = report.stopped
    why = stop.reason if stop else "The write did not finish."
    return (
        f"{why} Written: {', '.join(done) or 'none'}. "
        f"Not written: {', '.join(left) or 'none'}. Re-scan first, then try again."
    )


# --- re-scan (spec section 6) ---


def rescan_results(
    facts: FolderFacts, planned_paths: list[str], known: dict[str, str]
) -> ScanResult:
    """Compare what the browser reads now with the last known fingerprints. `known` maps a
    planned file to its last write, else its baseline. Only planned files are read (Phase 6)."""
    verify_facts(facts, planned_paths)
    by_path = {normalise_path(item.path): item for item in facts.files}
    items = [
        ScanItem(
            path=path, outcome=_file_outcome(by_path.get(normalise_path(path)), known.get(path))
        )
        for path in planned_paths
    ]
    return ScanResult(items=items)


def _file_outcome(fact: FileFact | None, last: str | None):
    if fact is None or not fact.exists or fact.text is None:
        # A planned new file that was never written is not "missing": there is nothing to lose.
        return "missing" if last is not None else "unchanged"
    return "unchanged" if last is not None and fingerprint(fact.text) == last else "changed"
