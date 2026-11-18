"""Step 2 of the index job: tag the programs (fix 11-3, D-C; AH-8, AH-9).

AS400 picture: the second step of one submitted job. It runs after the index is saved; a failure
here never takes the saved index away. Never logs code, prompt or reply.
"""

from pathlib import Path

from agents import da_admin_job as job
from agents.da_admin_modules import module_paths
from agents.da_admin_tag_store import read_store
from agents.da_admin_tagger import ScriptedTaggerClient, TagRun, paths_to_tag, run_tagging
from agents.da_llm_client import get_llm_client
from configs.da_config import Settings
from pydantic_classes.da_rulebook_models import Policy

TAGS_NOT_SAVED = "The index is saved; the tags were not saved."


def pick_client(settings: Settings, policy: Policy):
    """Home (fake provider) answers from the script; work uses the tagger role's model."""
    if settings.llm_provider == "fake":
        return ScriptedTaggerClient()
    return get_llm_client("tagger", settings, policy.tagger_model)


def tag_programs(
    policy: Policy,
    settings: Settings,
    started_by: str,
    mode: str,
    root: Path,
    out: Path,
    client=None,
) -> TagRun:
    """Full tags every program, Delta only new or changed ones. No cap: the job tags everything.

    Stop is all or nothing for tags: the index stays, no new tags are saved."""
    paths = module_paths(policy.index_folder_scope, out)
    exclusions = [e.pattern for e in policy.index_exclusions]
    todo, _ = paths_to_tag(
        paths, read_store(out), root, mode == "delta", max(len(paths), 1), exclusions
    )
    job.progress(out, 0, len(todo), step=2)
    return run_tagging(
        todo, root, policy.capabilities, client or pick_client(settings, policy), started_by,
        exclusions, out, None, lambda done, total: job.progress(out, done, total, step=2),
        stop=lambda: job.stop_requested(out),
    )
