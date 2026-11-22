"""The AI program tagger core (fix 11-2, section 3). One AI call per module, Admin approves later.

AS400 picture: a batch job that reads every source member once and writes one line per member to a
tag file. The AI only proposes; nothing here changes the rulebook. Never logs code, prompt or reply.
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import Path

from agents.da_admin_meaning import UNASSIGNED, capability_of
from agents.da_admin_tag_store import read_store, save_store
from agents.da_reply_reader import read_json_object
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
KEPT_RUNS = 10
# Fix G5 R3: why a program could not be read (never the reply text itself).
NO_JSON, BAD_CAPABILITY, BAD_CONFIDENCE = "no_json", "bad_capability", "bad_confidence"
BAD_NEW_NAME, EMPTY_SUMMARY, CALL_FAILED = "bad_new_name", "empty_summary", "call_failed"
RETRY_LINE = "Reply with the JSON object only."
UNREADABLE_SUMMARY = "AI could not read this program"
MANY_UNREADABLE_SHARE = 0.30
MANY_UNREADABLE = "Many programs could not be read: check the AI model."
NEW ="new"  # the AI suggests a capability that is not in the list (Fix G4, S1)
NEW_NAME_MIN, NEW_NAME_MAX, NEW_DESCRIPTION_MAX = 2, 40, 120
MODULE_LINE = "Module: "
# Fix G6 S6: an empty catalog tells the AI to suggest a new area for each program.
NO_CAPABILITIES = (
    "No capabilities exist yet. Suggest a new one for this program; use a short business area name."
)
STOPPED = "Stopped: the new tags were dropped, the new index stays."

STATE_PROPOSED, STATE_APPROVED, STATE_REJECTED, STATE_MATCHED = (
    "proposed", "approved", "rejected", "matched",
)
STATE_UNREADABLE = "unreadable"  # Fix G5 R5: the AI answered, but nothing usable came back


@dataclass(frozen=True)
class TagRun:
    saved: bool
    scanned: int
    proposed: int
    skipped: list[str] = field(default_factory=list)
    message: str = ""
    reasons: dict[str, int] = field(default_factory=dict)  # reason word to how many programs


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
    names = "\n".join(f"- {c.name}: {c.description}" for c in capabilities) or NO_CAPABILITIES
    return PROMPT_FILE.read_text(encoding="utf-8").format(
        path=path, capabilities=names, cut_note=note, code="\n".join(lines[:MAX_CODE_LINES])
    )


def _cut(text: str, limit: int) -> str:
    """Fix G5 R2: too long is cut at a word with "...", never rejected."""
    text = text.strip()
    if len(text) <= limit:
        return text
    room = text[: limit - 3]
    return (room.rsplit(" ", 1)[0] if " " in room else room).rstrip(" ,;:.") + "..."


def parse_reply(text: str, capabilities: list[Capability]) -> dict | None:
    """The checked reply, or None when it cannot be read (see read_reply for why)."""
    return read_reply(text, capabilities)[0]


def read_reply(text: str, capabilities: list[Capability]) -> tuple[dict | None, str]:
    """(the checked and cleaned reply, "") or (None, one reason word) (Fix G5 R2, R3)."""
    data = read_json_object(text)
    if data is None or not all(key in data for key in ("summary", "capability", "confidence")):
        return None, NO_JSON
    summary, reason = data["summary"], data.get("reason", "")
    if not isinstance(summary, str) or not summary.strip():
        return None, EMPTY_SUMMARY
    known = {name_key(c.name): c.name for c in capabilities} | {"none": "none", NEW: NEW}
    capability = known.get(name_key(str(data["capability"])))  # ignoring case and spaces
    if capability is None:
        return None, BAD_CAPABILITY
    confidence = str(data["confidence"]).strip().lower()
    if confidence not in CONFIDENCE:
        return None, BAD_CONFIDENCE
    checked = {"summary": _cut(summary, SUMMARY_MAX), "capability": capability,
               "confidence": confidence, "reason": _cut(str(reason or ""), REASON_MAX),
               "new_name": "", "new_description": ""}
    if capability == NEW:
        return _checked_new(checked, data, capabilities)
    return checked, ""


def clean_name(name: str) -> str:
    """"Upload & Ingestion" becomes "Upload and Ingestion": "&" to "and", other symbols dropped."""
    name = name.replace("&", " and ")
    kept = "".join(ch for ch in name if ch.isalnum() or ch in " -")
    return " ".join(kept.split())


def _checked_new(
    checked: dict, data: dict, capabilities: list[Capability]
) -> tuple[dict | None, str]:
    """S2: a `new` needs a plain name and a short description; a known name is a normal proposal."""
    name, description = data.get("new_name"), data.get("new_description")
    if not (isinstance(name, str) and isinstance(description, str)):
        return None, BAD_NEW_NAME
    if any(mark in name for mark in "/\\.:"):  # a path or file name is no capability name
        return None, BAD_NEW_NAME
    name, description = clean_name(name), _cut(description, NEW_DESCRIPTION_MAX)
    if not (NEW_NAME_MIN <= len(name) <= NEW_NAME_MAX) or not description:
        return None, BAD_NEW_NAME
    for capability in capabilities:
        if name_key(capability.name) == name_key(name):
            return {**checked, "capability": capability.name}, ""
    return {**checked, "new_name": name, "new_description": description}, ""


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
            if entry and entry.get("state") == STATE_UNREADABLE:
                todo.append(path)  # Fix G5: an unreadable program is tried again on every run
                continue
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
    """Tag the given modules. Good tags are always saved (Fix G5 R5); a program that cannot be
    read is saved as `unreadable` with its reason. `stop()` true between modules drops the whole
    run (the saved tags stay as they were)."""
    when = (now or datetime.now()).isoformat(timespec="seconds")
    sendable = [p for p in paths if is_sendable(p, exclusions or [])]
    entries: dict[str, dict] = {}
    skipped: list[str] = []
    reasons: Counter = Counter()
    model = getattr(client, "model", "")
    for number, path in enumerate(sendable, start=1):
        if stop and stop():
            return TagRun(False, number - 1, 0, skipped, STOPPED)
        entry, reason = _tag_one(path, root, capabilities, client)
        if entry is None:
            skipped.append(path)
            reasons[reason] += 1
            entry = _unreadable_entry(path, root, reason)
        entries[path] = {**entry, "model": model, "tagged_at": when}
        if progress:
            progress(number, len(sendable))
    scanned = len(sendable)
    proposed = sum(1 for e in entries.values() if e["state"] == STATE_PROPOSED)
    message = _run_message(scanned, len(skipped))
    logger.info("Tagger run: %s", _log_line(scanned, len(skipped), reasons))  # counts only
    store = read_store(directory)  # read again: Admin may have decided cards during the scan
    waiting = [m["new_name"] for m in store["modules"].values()
               if m.get("new_name") and m.get("state") == STATE_PROPOSED]
    group_new_names(entries, waiting)
    for path, entry in entries.items():
        current = store["modules"].get(path, {})
        if entry["state"] == STATE_UNREADABLE and current.get("state") not in (
            None, STATE_UNREADABLE
        ):
            continue  # a tag that was read before is never replaced by "could not read"
        decided = current.get("state") in (STATE_APPROVED, STATE_REJECTED)
        if decided and current.get("file_hash") == entry["file_hash"]:
            continue  # keep the Admin's decision on unchanged code
        if decided:  # code changed: refresh the text, keep the decision and the capability
            entry = {**entry, "state": current["state"],
                     "proposed_capability": current.get("proposed_capability", "")}
        store["modules"][path] = entry
    run = {"started_by": started_by, "started_at": when, "scanned": scanned,
           "proposed": proposed, "skipped": skipped, "reasons": dict(reasons)}
    store["runs"] = [run, *store["runs"]][:KEPT_RUNS]
    save_store(store, directory)
    return TagRun(True, scanned, proposed, skipped, message, dict(reasons))


def _run_message(scanned: int, unreadable: int) -> str:
    if not unreadable:
        return "Done."
    line = f"Tags: {scanned - unreadable} of {scanned} tagged, {unreadable} could not be read."
    many = scanned and unreadable / scanned > MANY_UNREADABLE_SHARE
    return f"{line} {MANY_UNREADABLE}" if many else line


def _log_line(scanned: int, unreadable: int, reasons: Counter) -> str:
    line = f"{scanned} programs, {scanned - unreadable} tagged"
    if not unreadable:
        return line
    words = ", ".join(f"{word} {count}" for word, count in sorted(reasons.items()))
    return f"{line}, {unreadable} could not be read ({words})"


def _unreadable_entry(path: str, root: Path, reason: str) -> dict:
    try:
        file_hash = text_hash((root / path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        file_hash = ""
    return {"file_hash": file_hash, "summary": UNREADABLE_SUMMARY, "proposed_capability": "",
            "confidence": "", "reason": reason, "state": STATE_UNREADABLE}


def _tag_one(
    path: str, root: Path, capabilities: list[Capability], client
) -> tuple[dict | None, str]:
    """(entry, "") or (None, reason word). One retry when the reply could not be read (R4)."""
    try:
        text = (root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, CALL_FAILED
    prompt = build_prompt(path, text, capabilities)
    checked, reason = None, CALL_FAILED
    for attempt in (prompt, f"{prompt}\n{RETRY_LINE}"):
        try:
            reply = client.complete(attempt)
        except Exception as error:  # noqa: BLE001 - one bad module must not stop the run
            logger.warning("Tagger call failed for one module: %s", type(error).__name__)
            return None, CALL_FAILED  # a dead server is not helped by asking twice
        checked, reason = read_reply(reply.text, capabilities)
        if checked is not None:
            break
    if checked is None:
        return None, reason
    matched = capability_of(path, capabilities) != UNASSIGNED
    new_name = "" if matched else checked["new_name"]  # a matched module needs no suggestion
    proposed = "" if checked["capability"] in ("none", NEW) else checked["capability"]
    suggestion = {"new_name": new_name, "new_description": checked["new_description"]}
    entry = {
        "file_hash": text_hash(text),
        "summary": checked["summary"],
        "proposed_capability": proposed,
        **(suggestion if new_name else {}),
        "confidence": checked["confidence"],
        "reason": checked["reason"],
        "state": STATE_MATCHED if matched else STATE_PROPOSED,
    }
    return entry, ""
