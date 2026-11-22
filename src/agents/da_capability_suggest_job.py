"""Fix G6 S4: "Suggest capabilities from the code" as a background job (same lock and progress bar
as every other Admin job). Cards are saved only at the end, so a crash leaves the old cards as
they were. Nothing is created in the catalog here.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

from agents import da_admin_job as job
from agents.da_admin_index import index_dir
from agents.da_admin_modules import module_paths, modules_by_capability
from agents.da_admin_rebuild import ALREADY_RUNNING, _lock_path, _take_lock, running_since
from agents.da_admin_tag_store import read_store
from agents.da_admin_tagger_job import pick_client
from agents.da_capability_suggest import STEP_GROUPING, STEP_MERGING, STEP_NAMING, suggest
from agents.da_code_graph import load_graph
from agents.da_group_cards import save_suggestions
from configs.da_config import Settings
from da_logging import get_logger
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)

BUTTON = "Suggest capabilities from the code"
FEW_CAPABILITIES = 5
MANY_UNASSIGNED = 0.3
NO_GRAPH = "The code links are not built yet. Run a Full rebuild first."
STEPS = (STEP_GROUPING, STEP_NAMING, STEP_MERGING)


class ScriptedGroupClient:
    """Home only: names a group by the top folder of its first program; merges nothing."""

    model = "fake-group-script"

    def complete(self, prompt: str, system: str | None = None):
        from agents.da_llm_client import LLMReply

        if "Suggested areas" in prompt:
            text = json.dumps({"merges": []})
        else:
            first = prompt.split("- ", 1)[1].split(":", 1)[0].split("\n", 1)[0]
            folder = first.split("/", 1)[0].removesuffix(".py").replace("_", " ").strip()
            text = json.dumps({"name": folder.title() or "Programs",
                               "description": "Programs that call each other a lot.",
                               "not_in_group": [], "confidence": "medium"})  # fmt: skip
        return LLMReply(text=text, provider="fake", model=self.model)


def should_offer(capability_count: int, unassigned: int, programs: int) -> bool:
    """The button shows with fewer than 5 capabilities or more than 30% of programs unassigned."""
    return capability_count < FEW_CAPABILITIES or (
        programs > 0 and unassigned / programs > MANY_UNASSIGNED
    )


def offer_for(policy: Policy, directory: Path | None = None) -> bool:
    """Show the button for this catalog and index? (No programs in the index: nothing to group.)"""
    paths = module_paths(policy.index_folder_scope, directory)
    assigned = {p for ps in modules_by_capability(policy.capabilities, paths).values() for p in ps}
    return bool(paths) and should_offer(len(policy.capabilities), len(paths) - len(assigned),
                                        len(paths))  # fmt: skip


def _summaries(out: Path) -> dict[str, str]:
    modules = read_store(out)["modules"]
    return {p: str(e.get("summary", "")) for p, e in modules.items() if isinstance(e, dict)}


def _run(policy, settings, started_by, started, directory, client) -> None:
    out = directory or index_dir()
    job.begin(out, started, started_by, "suggest", "Manual")
    try:
        graph = load_graph(out)
        if graph is None:
            job.fail(out, NO_GRAPH)
            return
        known = [c.name for c in policy.capabilities]

        def say(step: str) -> None:
            job.set_step_name(out, step, STEPS.index(step) + 1)

        exclusions = [e.pattern for e in policy.index_exclusions]
        named = suggest(
            graph, _summaries(out), client or _pick(settings, policy), known, say, exclusions
        )
        save_suggestions(named, out)
        job.set_end_line(out, f"{len(named)} capability suggestions from code links. Review them.")
    except Exception as error:  # a crash must free the lock and keep the old cards
        logger.warning("Capability suggestion failed: %s", type(error).__name__)
        job.fail(out, f"Suggesting capabilities failed: {type(error).__name__}")
    finally:
        _lock_path(out).unlink(missing_ok=True)


def _pick(settings: Settings, policy: Policy):
    if settings.llm_provider == "fake":
        return ScriptedGroupClient()
    return pick_client(settings, policy)


def start_suggest(
    policy: Policy, settings: Settings, started_by: str, now: datetime | None = None,
    directory: Path | None = None, wait: bool = False, client=None,
) -> tuple[bool, str]:
    started = now or datetime.now()
    if running_since(started, directory) is not None or not _take_lock(started, directory):
        return False, ALREADY_RUNNING
    args = (policy, settings, started_by, started, directory, client)
    thread = threading.Thread(target=_run, args=args, daemon=True)
    thread.start()
    if wait:
        thread.join()
    return True, "Suggesting capabilities from the code."
