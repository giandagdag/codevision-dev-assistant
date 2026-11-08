"""Shared helpers for the Phase 8 lane tests: a request at b_written, and scripted AI replies."""

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_refine_lanes as lanes
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_refine import read_all_records
from tests.da_build_play import build_state, ready_with_workspace


def written_request(settings):
    """A request at b_written, READY_FOR_REVIEW: built and written to the pretend folder."""
    request_id, folder = ready_with_workspace(settings)
    flow.start_build(settings, request_id, 0)
    assert loop.run_build(settings, request_id) == "done"
    job = flow.prepare_write(settings, request_id, flow.get_revision(settings, request_id))
    flow.save_write(
        settings, request_id, folder.run_job(job), flow.get_revision(settings, request_id)
    )
    assert build_state(settings, request_id).step == "b_written"
    return request_id, folder


def rev(settings, request_id) -> int:
    return lanes.get_refine_revision(settings, request_id)


def records_of(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_all_records(conn, request_id)


def lane_reply(lane, reason="Because.", criterion=None):
    return {"lane": lane, "reason": reason, "criterion_id": criterion}
