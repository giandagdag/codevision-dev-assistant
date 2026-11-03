"""Test helpers for the Workspace: a request at READY_TO_BUILD, a pretend folder, and a quick
way through the browser steps. The scripted Approach plan creates src/agents/excel_processor.py
and modifies src/agents/upload_validator.py (made-up names)."""

from agents import da_approach_flow as approach_flow
from agents import da_workspace_flow as flow
from tests.da_approach_play import at_tests, discovery_confirmed_id
from web.da_fake_browser_folder import FakeBrowserFolder

CREATE = "src/agents/excel_processor.py"
MODIFY = "src/agents/upload_validator.py"
ORIGINAL = "def validate(path):\n    return True\n"

# The practice folder from docs/workspace-work-test.md (P29): what the fake plan needs. The docs
# test reads these same lists, so the docs and the tests cannot drift apart.
PRACTICE_FOLDERS = ("src/web", "src/callbacks", "src/agents")
PRACTICE_FILE = MODIFY
PRACTICE_TEXT = "def validate(path): return True\n"


def ready_to_build_id(settings) -> str:
    request_id = discovery_confirmed_id(settings)
    view = at_tests(settings, request_id)
    approach_flow.accept_test_plan(settings, request_id, view.revision)
    return request_id


def practice_folder() -> FakeBrowserFolder:
    """The practice folder from the work-test steps: three empty folders and one one-line file."""
    return FakeBrowserFolder(
        name="practice", files={PRACTICE_FILE: PRACTICE_TEXT}, folders=set(PRACTICE_FOLDERS)
    )


def good_folder(name: str = "codevision", **changes) -> FakeBrowserFolder:
    """A pretend CodeVision clone that fits the scripted plan."""
    files = {
        "src/web/da_page.py": "# web\n",
        "src/callbacks/da_calls.py": "# callbacks\n",
        MODIFY: ORIGINAL,
    }
    files.update(changes.pop("files", {}))
    return FakeBrowserFolder(name=name, files=files, **changes)


def facts_of(settings, request_id, folder):
    view = flow.get_workspace_view(settings, request_id)
    return folder.facts(view.planned_paths, view.markers, request_id, view.max_file_kb)


def pick(settings, request_id, folder, revision=0):
    """All four hops with the pretend folder. Returns (view, judgement)."""
    facts = facts_of(settings, request_id, folder)
    judgement = flow.judge_facts(settings, request_id, facts, revision)
    if judgement.job is None:
        return judgement.view, judgement
    report = folder.run_job(judgement.job)
    return flow.save_check(settings, request_id, facts, report, revision), judgement


def texts(view, speaker=None):
    return [m.text for m in view.messages if speaker is None or m.speaker == speaker]
