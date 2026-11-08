"""A rebuild over his edit stops at b_conflicts and writes nothing (Phase 8 step 10a): test 8-27."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agents import da_build_agent as agent
from agents import da_build_loop as loop
from agents import da_refine_fixit as fixit
from agents import da_tester_flow as tflow
from agents.da_workspace_checks import fingerprint, line_ending_of
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_refine import read_conflicts
from db_table_functions.db_tbl_da_workspace import insert_workspace_file, read_file_versions
from pydantic_classes.da_workspace_models import WorkspaceFile
from tests.da_approach_play import events_of
from tests.da_build_play import build_state
from tests.da_refine_play import rev, written_request

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def _factory(replace_with: str):
    """The real fake AI, except a code reply that changes his first line."""

    def make(settings, role):
        real = agent.get_build_client(settings, role)

        class Client:
            model = real.model

            def complete(self, prompt, system=None):
                reply = real.complete(prompt, system)
                if agent.CODE_MARKER not in prompt:
                    return reply
                block = f"<<<<<<< FIND\n# my note\n=======\n{replace_with}\n>>>>>>> REPLACE\n"
                return SimpleNamespace(provider=reply.provider, model=reply.model, text=block)

        return Client()

    return make


def _he_edits(settings, request_id, path):
    with open_db(settings.db_path) as conn:
        newest = read_file_versions(conn, request_id, path)[-1]
        text = "# my note\n" + newest.text
        insert_workspace_file(
            conn,
            WorkspaceFile(
                request_id=request_id,
                path=path,
                file_version=1,
                kind="scanned",
                text=text,
                fingerprint=fingerprint(text),
                line_ending=line_ending_of(text),
                mode="picker",
                approach_version=newest.approach_version,
            ),
            datetime.now(UTC),
        )
        conn.commit()


def test_8_27_rebuild_over_his_lines_stops_at_b_conflicts(settings):
    request_id, _ = written_request(settings)
    rows = tflow.get_tester_view(settings, request_id).rows
    finding = next(r.finding for r in rows if r.finding.severity == "should_fix")
    _he_edits(settings, request_id, finding.file)
    fixit.fix_it(settings, request_id, rev(settings, request_id), finding.finding_id)

    result = loop.run_build(settings, request_id, _factory("# ai note"), build_number=2)

    assert result == "done"
    state = build_state(settings, request_id)
    assert state.step == "b_conflicts" and state.write_state == "not_written"
    with open_db(settings.db_path) as conn:
        found = read_conflicts(conn, request_id, 2)
    assert [c.conflict_id for c in found] == ["C-1"]
    assert found[0].path == finding.file and found[0].choice is None
    assert "# my note" in found[0].his_lines and "# ai note" in found[0].ai_lines
    assert len(events_of(settings, request_id, "conflicts_found")) == 1
