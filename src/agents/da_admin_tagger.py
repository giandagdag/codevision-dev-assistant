"""The AI program tagger core (fix 11-2, section 3). One AI call per module, Admin approves later.

AS400 picture: a batch job that reads every source member once and writes one line per member to a
tag file. The AI only proposes; nothing here changes the rulebook. Never logs code, prompt or reply.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import Path

from agents.da_admin_meaning import UNASSIGNED, capability_of
from agents.da_admin_tag_store import read_store, save_store
from agents.da_search_index import DATA_FOLDER, looks_secret
from da_logging import get_logger
from pydantic_classes.da_rulebook_models import Capability

logger = get_logger(__name__)

PROMPT_FILE = DATA_FOLDER / "da_tagger_prompt.md"
FAKE_SCRIPT_FILE = DATA_FOLDER / "da_tagger_fake_script.json"
MAX_CODE_LINES = 200
SUMMARY_MAX = 120
REASON_MAX = 160
CONFIDENCE = ("high", "medium", "low")
MAX_SKIPPED_SHARE = 0.10
KEPT_RUNS = 10
NOT_SAVED = "Not saved: over 10% failed, the old tags stay."
MODULE_LINE = "Module: "

STATE_PROPOSED, STATE_APPROVED, STATE_REJECTED, STATE_MATCHED = (
    "proposed", "approved", "rejected", "matched",
)


@dataclass(frozen=True)
class TagRun:
    saved: bool
    scanned: int
    proposed: int
    skipped: list[str] = field(default_factory=list)
    message: str = ""


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_sendable(path: str, exclusions: list[str]) -> bool:
    """Never send an assistant file (da_), a secret-looking path or an excluded path (AG-10)."""
    parts = path.replace("\\", "/").split("/")
    if any(part.lower().startswith("da_") for part in parts) or looks_secret(path):
        return False
    return not any(fnmatchcase(path.lower(), pattern.lower()) for pattern in exclusions)


def build_prompt(path: str, text: str, capabilities: list[Capability]) -> str:
    """The prompt: path, first 200 lines, capability names and descriptions. No senior names."""
    lines = text.splitlines()
    cut = len(lines) > MAX_CODE_LINES
    note = f" (first {MAX_CODE_LINES} of {len(lines)} lines)" if cut else ""
    names = "\n".join(f"- {c.name}: {c.description}" for c in capabilities)
    return PROMPT_FILE.read_text(encoding="utf-8").format(
        path=path, capabilities=names, cut_note=note, code="\n".join(lines[:MAX_CODE_LINES])
    )


def parse_reply(text: str, capabilities: list[Capability]) -> dict | None:
    """The checked reply, or None when anything is off (that module is skipped)."""
    body = text.strip()
    if body.startswith("```"):  # some models wrap JSON in a fence
        body = body.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(body)
        summary, reason = data["summary"], data["reason"]
        capability, confidence = data["capability"], data["confidence"]
    except ValueError, KeyError, TypeError:
        return None
    names = {c.name for c in capabilities} | {"none"}
    ok = (
        isinstance(summary, str) and 1 <= len(summary.strip()) <= SUMMARY_MAX
        and isinstance(reason, str) and len(reason) <= REASON_MAX
        and capability in names and confidence in CONFIDENCE
    )
    if not ok:
        return None
    return {"summary": summary.strip(), "capability": capability, "confidence": confidence,
            "reason": reason.strip()}


class ScriptedTaggerClient:
    """Home only: answers from `da_tagger_fake_script.json` by the module line in the prompt."""

    model = "fake-tagger-script"

    def __init__(self, script: dict | None = None):
        if script is None:
            script = json.loads(FAKE_SCRIPT_FILE.read_text(encoding="utf-8"))["replies"]
        self._replies = script

    def complete(self, prompt: str, system: str | None = None):
        from agents.da_llm_client import LLMReply  # here: avoids a heavier import at load time

        lines = [ln for ln in prompt.splitlines() if ln.startswith(MODULE_LINE)]
        path = lines[0][len(MODULE_LINE):].strip() if lines else ""
        reply = self._replies.get(path, "")
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return LLMReply(text=text, provider="fake", model=self.model)


def paths_to_tag(
    paths: list[str], store: dict, root: Path, only_changed: bool, limit: int
) -> tuple[list[str], int]:
    """(paths for this run, how many wait for the next run). New or changed only when asked."""
    todo = []
    for path in paths:
        if only_changed:
            entry = store["modules"].get(path)
            try:
                same = entry and entry.get("file_hash") == text_hash(
                    (root / path).read_text(encoding="utf-8", errors="replace")
                )
            except OSError:
                same = False
            if same:
                continue
        todo.append(path)
    return todo[:limit], max(0, len(todo) - limit)


def run_tagging(
    paths: list[str],
    root: Path,
    capabilities: list[Capability],
    client,
    started_by: str,
    exclusions: list[str] | None = None,
    directory: Path | None = None,
    now: datetime | None = None,
    progress=None,
) -> TagRun:
    """Tag the given modules. Saved together or not at all (over 10% skipped = not saved)."""
    when = (now or datetime.now()).isoformat(timespec="seconds")
    store = read_store(directory)
    sendable = [p for p in paths if is_sendable(p, exclusions or [])]
    entries: dict[str, dict] = {}
    skipped: list[str] = []
    for number, path in enumerate(sendable, start=1):
        entry = _tag_one(path, root, capabilities, client)
        if entry is None:
            skipped.append(path)
        else:
            entries[path] = {**entry, "model": getattr(client, "model", ""), "tagged_at": when}
        if progress:
            progress(number, len(sendable))
    scanned = len(sendable)
    proposed = sum(1 for e in entries.values() if e["state"] == STATE_PROPOSED)
    if scanned and len(skipped) / scanned > MAX_SKIPPED_SHARE:
        logger.warning("Tagger run not saved: %d of %d modules skipped", len(skipped), scanned)
        return TagRun(False, scanned, proposed, skipped, NOT_SAVED)
    store["modules"].update(entries)
    run = {"started_by": started_by, "started_at": when, "scanned": scanned,
           "proposed": proposed, "skipped": skipped}
    store["runs"] = [run, *store["runs"]][:KEPT_RUNS]
    save_store(store, directory)
    return TagRun(True, scanned, proposed, skipped, "Done.")


def _tag_one(path: str, root: Path, capabilities: list[Capability], client) -> dict | None:
    try:
        text = (root / path).read_text(encoding="utf-8", errors="replace")
        reply = client.complete(build_prompt(path, text, capabilities))
    except Exception as error:  # noqa: BLE001 - one bad module must not stop the run; log the type only
        logger.warning("Tagger call failed for one module: %s", type(error).__name__)
        return None
    checked = parse_reply(reply.text, capabilities)
    if checked is None:
        return None
    matched = capability_of(path, capabilities) != UNASSIGNED
    return {
        "file_hash": text_hash(text),
        "summary": checked["summary"],
        "proposed_capability": "" if checked["capability"] == "none" else checked["capability"],
        "confidence": checked["confidence"],
        "reason": checked["reason"],
        "state": STATE_MATCHED if matched else STATE_PROPOSED,
    }
