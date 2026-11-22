"""Fix G6 S2/S3: suggest a first catalog from code links. The AI only names groups of programs.

AS400 picture: the links decide which programs sit together (like a "where used" cross reference);
the AI only reads paths and one-line summaries to find a business name. Never code text, and
nothing here creates a capability: the results are cards for Admin to decide on.
Never logs a prompt or a reply.
"""

from dataclasses import dataclass

from agents.da_admin_tagger import (
    CONFIDENCE,
    NEW_DESCRIPTION_MAX,
    NEW_NAME_MAX,
    NEW_NAME_MIN,
    RETRY_LINE,
    _cut,
    clean_name,
    is_sendable,
)
from agents.da_code_clusters import Group
from agents.da_reply_reader import read_json_object
from agents.da_search_index import DATA_FOLDER
from da_logging import get_logger

logger = get_logger(__name__)

PROMPT_FILE = DATA_FOLDER / "da_group_prompt.md"
MAX_PROGRAMS_IN_PROMPT = 40


@dataclass(frozen=True)
class NamedGroup:
    name: str
    description: str
    programs: tuple[str, ...]  # the group without the paths the AI said do not fit
    confidence: str
    folders: tuple[str, ...]
    inside: int
    outside: int


def build_group_prompt(programs: list[str], summaries: dict[str, str]) -> str:
    """Paths and saved one-line summaries only, at most 40 programs."""
    shown = programs[:MAX_PROGRAMS_IN_PROMPT]
    cut = f" (first {len(shown)} of {len(programs)})" if len(programs) > len(shown) else ""
    lines = "\n".join(f"- {p}: {summaries.get(p, '')}".rstrip(": ") for p in shown)
    return PROMPT_FILE.read_text(encoding="utf-8").format(programs=lines, cut_note=cut)


def read_group_reply(text: str, programs: tuple[str, ...]) -> dict | None:
    """The checked reply (name, description, not_in_group, confidence) or None."""
    data = read_json_object(text)
    if data is None:
        return None
    name, description = data.get("name"), data.get("description", "")
    if not isinstance(name, str) or not isinstance(description, str):
        return None
    name = clean_name(name)
    confidence = str(data.get("confidence", "")).strip().lower()
    if not (NEW_NAME_MIN <= len(name) <= NEW_NAME_MAX) or confidence not in CONFIDENCE:
        return None
    left_out = data.get("not_in_group", [])
    left_out = [p for p in left_out if p in programs] if isinstance(left_out, list) else []
    return {"name": name, "description": _cut(description, NEW_DESCRIPTION_MAX),
            "not_in_group": left_out, "confidence": confidence}  # fmt: skip


def name_group(group: Group, summaries: dict[str, str], client) -> NamedGroup | None:
    """One AI call for one group, one retry when the reply cannot be read. None = could not name."""
    sendable = [p for p in group.programs if is_sendable(p, [])]
    if not sendable:
        return None
    prompt = build_group_prompt(sendable, summaries)
    for attempt in (prompt, f"{prompt}\n{RETRY_LINE}"):
        try:
            reply = client.complete(attempt)
        except Exception as error:  # noqa: BLE001 - one bad group must not stop the job
            logger.warning("Group naming call failed: %s", type(error).__name__)
            return None
        checked = read_group_reply(reply.text, tuple(sendable))
        if checked:
            kept = tuple(p for p in group.programs if p not in checked["not_in_group"])
            return NamedGroup(
                checked["name"], checked["description"], kept, checked["confidence"],
                group.folders, group.inside, group.outside,
            )
    return None
