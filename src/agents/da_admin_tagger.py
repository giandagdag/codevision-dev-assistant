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
NEW = "new"  # the AI suggests a capability that is not in the list (Fix G4, S1)
NEW_NAME_MIN, NEW_NAME_MAX, NEW_DESCRIPTION_MAX = 2, 40, 120
MODULE_LINE = "Module: "
STOPPED = "Stopped: the new tags were dropped, the new index stays."

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
    names = {c.name for c in capabilities} | {"none", NEW}
    ok = (
        isinstance(summary, str) and 1 <= len(summary.strip()) <= SUMMARY_MAX
        and isinstance(reason, str) and len(reason) <= REASON_MAX
        and capability in names and confidence in CONFIDENCE
    )
    if not ok:
        return None
    checked = {"summary": summary.strip(), "capability": capability, "confidence": confidence,
               "reason": reason.strip(), "new_name": "", "new_description": ""}
    if capability == NEW:
        return _checked_new(checked, data, capabilities)
    return checked


def _checked_new(checked: dict, data: dict, capabilities: list[Capability]) -> dict | None:
    """S2: a `new` needs a plain name and a short description; a known name is a normal proposal."""
    name, description = data.get("new_name"), data.get("new_description")
    if not (isinstance(name, str) and isinstance(description, str)):
        return None
    name, description = " ".join(name.split()), description.strip()
    plain = name.replace(" ", "").replace("-", "").isalnum()  # no path, dots or symbols
    if not (NEW_NAME_MIN <= len(name) <= NEW_NAME_MAX and plain):
        return None
    if not 1 <= len(description) <= NEW_DESCRIPTION_MAX:
        return None
    for capability in capabilities:
        if name_key(capability.name) == name_key(name):
            return {**checked, "capability": capability.name}
    return {**checked, "new_name": name, "new_description": description}


def name_key(name: str) -> str:
    """Same name ignoring case, spaces and a plural "s" (S3)."""
    return name.lower().replace(" ", "").removesuffix("s")


def group_new_names(entries: dict[str, dict], known: list[str]) -> None:
    """S3: modules suggesting the same new name share the first spelling seen (in place)."""
    first = {name_key(name): name for name in known}
    for entry in entries.values():
        if entry.get("new_name"):
            entry["new_name"] = first.setdefault(name_key(entry["new_name"]), entry["new_name"])


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
    paths: list[str],
    store: dict,
    root: Path,
    only_changed: bool,
    limit: int,
    exclusions: list[str] | None = None,
) -> tuple[list[str], int]:
    """(paths for this run, how many wait for the next run). New or changed only when asked.

    Programs that are never sent do not use up places; untagged ones go first, so every scan
    makes progress over the rest."""
    todo = []
    for path in sorted(
        (p for p in paths if is_sendable(p, exclusions or [])),
        key=lambda p: p in store["modules"],  # False (untagged) sorts first; sort is stable
    ):
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
    stop=None,
) -> TagRun:
    """Tag the given modules. Saved together or not at all (over 10% skipped = not saved).
    `stop()` true between modules drops the whole run (the saved tags stay as they were)."""
    when = (now or datetime.now()).isoformat(timespec="seconds")
    sendable = [p for p in paths if is_sendable(p, exclusions or [])]
    entries: dict[str, dict] = {}
    skipped: list[str] = []
    for number, path in enumerate(sendable, start=1):
        if stop and stop():
            return TagRun(False, number - 1, 0, skipped, STOPPED)
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
    store = read_store(directory)  # read again: Admin may have decided cards during the scan
    waiting = [m["new_name"] for m in store["modules"].values()
               if m.get("new_name") and m.get("state") == STATE_PROPOSED]
    group_new_names(entries, waiting)
    for path, entry in entries.items():
        current = store["modules"].get(path, {})
        decided = current.get("state") in (STATE_APPROVED, STATE_REJECTED)
        if decided and current.get("file_hash") == entry["file_hash"]:
            continue  # keep the Admin's decision on unchanged code
        if decided:  # code changed: refresh the text, keep the decision and the capability
            entry = {**entry, "state": current["state"],
                     "proposed_capability": current.get("proposed_capability", "")}
        store["modules"][path] = entry
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
    new_name = "" if matched else checked["new_name"]  # a matched module needs no suggestion
    proposed = "" if checked["capability"] in ("none", NEW) else checked["capability"]
    suggestion = {"new_name": new_name, "new_description": checked["new_description"]}
    return {
        "file_hash": text_hash(text),
        "summary": checked["summary"],
        "proposed_capability": proposed,
        **(suggestion if new_name else {}),
        "confidence": checked["confidence"],
        "reason": checked["reason"],
        "state": STATE_MATCHED if matched else STATE_PROPOSED,
    }
