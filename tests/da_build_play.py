"""Test helpers for the Build: a made-up build context and the nine scripted test cases.
Nothing here calls an AI."""

from agents.da_build_agent import BuildContext
from pydantic_classes.da_approach_models import ApproachReply, ApproachVersion, TestCase
from tests.da_approach_samples import REQUEST_ID, good_plan, sample_record

CREATE = "src/agents/excel_processor.py"
MODIFY = "src/agents/upload_validator.py"
ORIGINAL = "def validate(path):\n    return True\n"


def make_cases(count: int = 9, developer: tuple[int, ...] = ()) -> list[TestCase]:
    """T-1 to T-<count> over criteria AC-1 to AC-3. Numbers in `developer` are 'Yours' cases."""
    return [
        TestCase(
            test_id=f"T-{number}",
            criterion_id=f"AC-{(number - 1) % 3 + 1}",
            given=f"a workbook for case {number}",
            expect=f"the result for case {number} is visible",
            source="developer" if number in developer else "tester",
        )
        for number in range(1, count + 1)
    ]


def make_approach(request_id: str = REQUEST_ID) -> ApproachVersion:
    return ApproachVersion(
        request_id=request_id,
        approach_version=1,
        source="proposal",
        record_version=1,
        rulebook_version=1,
        discovery_round=1,
        plan=ApproachReply.model_validate(good_plan()),
    )


def make_context(seed_rulebook, cases: int = 9, **policy_changes) -> BuildContext:
    policy = seed_rulebook.policy.model_copy(update=policy_changes)
    return BuildContext(
        charter=seed_rulebook.charter,
        record=sample_record(),
        approach=make_approach(),
        cases=make_cases(cases),
        policy=policy,
    )


# --- a request ready to build, and ways to look at what the build saved ---


def ready_with_workspace(settings, folder=None):
    """A request at READY_TO_BUILD with workspace step ws_ready in a pretend folder."""
    from tests.da_workspace_play import good_folder, pick, ready_to_build_id

    request_id = ready_to_build_id(settings)
    folder = folder or good_folder()
    pick(settings, request_id, folder)
    return request_id, folder


def build_state(settings, request_id):
    from agents import da_build_flow as flow

    return flow.get_state(settings, request_id)


def request_status(settings, request_id) -> str:
    from db_table_functions.db_tbl_da_requests import get_request

    return get_request(settings.db_path, request_id).status


def event_types(settings, request_id) -> list[str]:
    from tests.da_approach_play import event_types as approach_event_types

    return approach_event_types(settings, request_id)


class RecordingFactory:
    """A client factory for the loop that remembers every prompt, by role, and the AI model."""

    def __init__(self):
        from agents import da_build_agent as agent

        self.agent = agent
        self.calls: list[tuple[str, str]] = []

    def __call__(self, settings, role):
        real = self.agent.get_build_client(settings, role)
        calls = self.calls

        class Recorder:
            model = real.model

            def complete(self, prompt, system=None):
                calls.append((role, prompt))
                return real.complete(prompt, system)

        return Recorder()

    def prompts(self, role=None):
        return [prompt for who, prompt in self.calls if role in (None, who)]

    def code_calls(self):
        marker = self.agent.CODE_MARKER
        return [p for p in self.prompts() if marker in p]


def chat(settings, request_id, speaker=None) -> list[str]:
    """The chat lines saved for a request, oldest first."""
    from db_table_functions.da_db import open_db
    from db_table_functions.db_tbl_da_understand import read_messages

    with open_db(settings.db_path) as conn:
        found = read_messages(conn, request_id)
    return [m.text for m in found if speaker is None or m.speaker == speaker]


def rounds_of(settings, request_id, build=1):
    from db_table_functions.da_db import open_db
    from db_table_functions.db_tbl_da_build import read_rounds

    with open_db(settings.db_path) as conn:
        return read_rounds(conn, request_id, build)


def files_of(settings, request_id, build=1, kind=None):
    from db_table_functions.da_db import open_db
    from db_table_functions.db_tbl_da_build import read_build_files

    with open_db(settings.db_path) as conn:
        return read_build_files(conn, request_id, build, kind)


def run_row(settings, request_id, build=1):
    from db_table_functions.da_db import open_db
    from db_table_functions.db_tbl_da_build import read_build_run

    with open_db(settings.db_path) as conn:
        return read_build_run(conn, request_id, build)


def progress_of(settings, request_id, build=1):
    from db_table_functions.da_db import open_db
    from db_table_functions.db_tbl_da_build import read_progress

    with open_db(settings.db_path) as conn:
        return read_progress(conn, request_id, build)
