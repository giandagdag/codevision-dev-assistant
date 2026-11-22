"""Try the tagger on one program (Fix G5 R7). Saves nothing.

AS400 picture: run one source member through the batch step on a test run and read the print-out,
without writing the tag file. One AI call, under the same lock as the index job. Never logs code or
the reply.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agents.da_admin_modules import module_paths
from agents.da_admin_rebuild import (
    ALREADY_RUNNING,
    _lock_path,
    _take_lock,
    running_since,
    source_folder,
)
from agents.da_admin_tagger import build_prompt, is_sendable, read_reply
from agents.da_admin_tagger_job import pick_client
from configs.da_config import Settings
from da_logging import get_logger
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)

RAW_MAX = 2000


@dataclass(frozen=True)
class TryResult:
    message: str  # one plain line (empty when the call ran)
    raw: str = ""  # the AI's reply, first RAW_MAX characters
    result: dict | None = None  # the reader's cleaned reply
    reason: str = ""  # why the reader refused it (a word), "" when it was read


def try_tagger(
    policy: Policy, settings: Settings, path: str, directory: Path | None = None, client=None
) -> TryResult:
    if path not in module_paths(policy.index_folder_scope, directory):
        return TryResult("Pick a program from the list.")
    if not is_sendable(path, [e.pattern for e in policy.index_exclusions]):
        return TryResult("That program is never sent to the AI.")
    if running_since(None, directory) is not None or not _take_lock(datetime.now(), directory):
        return TryResult(ALREADY_RUNNING)
    try:
        root = source_folder(policy, settings.llm_provider, settings)
        text = (root / path).read_text(encoding="utf-8", errors="replace")
        prompt = build_prompt(path, text, policy.capabilities)
        reply = (client or pick_client(settings, policy)).complete(prompt).text
    except Exception as error:  # noqa: BLE001 - the panel shows a line, never a crash
        logger.warning("Try the tagger failed: %s", type(error).__name__)
        return TryResult(f"The call failed ({type(error).__name__}).")
    finally:
        _lock_path(directory).unlink(missing_ok=True)
    result, reason = read_reply(reply, policy.capabilities)
    return TryResult("", reply[:RAW_MAX], result, reason)


def try_text(r: TryResult) -> str:
    """The reader's result and reason in plain words."""
    if r.message:
        return r.message
    if r.result is None:
        return f"Could not be read. Reason: {r.reason}."
    got = r.result
    return f"Read: {got['capability']}, {got['confidence']} confidence. {got['summary']}"
