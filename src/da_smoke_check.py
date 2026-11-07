"""Proves Phases 0, 1, 2A, 2C, 2D, 3 and 4 work end to end.

Run: .venv\\Scripts\\python src\\da_smoke_check.py
"""

import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from agents import da_approach_flow as approach
from agents import da_build_flow as build
from agents import da_build_loop as build_loop
from agents import da_tester_flow as tester_flow
from agents import da_workspace_flow as workspace
from agents.da_discover_flow import confirm_discovery, start_discovery
from agents.da_llm_client import LLMClient, LLMClientError, get_llm_client
from agents.da_search_index import FakeSearchIndex, search_safely
from agents.da_understand_flow import (
    ALWAYS_VISIBLE,
    PROCEED_OPTION,
    choose_option,
    create_understand_request,
    submit_form,
)
from configs.da_config import DEFAULT_ENV_FILE, ConfigError, Settings, load_settings
from da_llm_ping import ping
from da_load_starter_rulebook import load_starter_rulebook
from db_table_functions.da_db import DatabaseBusyError, open_db
from db_table_functions.db_tbl_da_audit import add_audit_event, list_audit_events
from db_table_functions.db_tbl_da_requests import create_request, get_rulebook_for_request
from db_table_functions.db_tbl_da_rulebook import (
    SEED_RULEBOOK_FILE,
    RulebookError,
    list_versions,
    load_rulebook_file,
    publish_first_version,
    restore_version,
    save_new_version,
)
from db_table_functions.db_tbl_da_understand import (
    UnderstandError,
    get_confirmed_record,
    list_messages,
)
from pydantic_classes.da_discovery_models import SearchFilters
from pydantic_classes.da_models import (
    STATUS_CONFIRMED,
    STATUS_DISCOVERY_CONFIRMED,
    STATUS_READY_TO_BUILD,
    StatusMoveError,
)
from pydantic_classes.da_rulebook_models import Rulebook
from web.da_fake_browser_folder import FakeBrowserFolder
from web.da_fake_onprem_server import running_fake_onprem_server

SAMPLE_TITLE = "Smoke check: sample change to a made-up loan program"
SAMPLE_DEVELOPER = "dev-0001"
SAMPLE_ADMIN = "admin-0001"
SAMPLE_PROMPT = "Say hello to the Developer Assistant team in one sentence."
CHANGED_RULE_ID = "CV-PY-002"

# The made-up Excel example from the demo. The fake script ignores the text, but the
# answers are still checked (secrets, length) and saved in the chat like real ones.
SAMPLE_FIRST_MESSAGE = "Users keep asking if they can upload Excel files. Can we support that?"
SAMPLE_ANSWERS = (
    "Yes. Teams keep inventories in Excel and convert them to PDF before uploading.",
    "The upload screen only accepts PDF and DOCX. Excel files are rejected.",
    "Validate the Excel file, extract the worksheets, and pass them into ingestion.",
    ".xlsx workbooks in, the normal ingestion format out. Reject empty or corrupted files.",
)
SAMPLE_REFERENCE = "Use the existing PDF processing as a reference."
SAMPLE_ONPREM_MODEL = "fake-qwen"
SAMPLE_CASE = "A workbook where every visible sheet is empty should be rejected as empty."
# The line every Tester test-plan prompt carries (see agents/da_tester_agent.py).
TESTER_MARKER = "Task: write a test plan"
EXPECTED_CRITERIA = 7  # the fake script's six criteria plus the one the hidden-sheet decision adds


def run_smoke_check(settings: Settings) -> int:
    """Print the Phase 0, 1 and 2A checks. Return 0 if all passed, 1 if one stopped."""
    print(f"1. Active AI provider: {settings.llm_provider}")
    try:
        # Set up the AI client first, so a setup problem stops us before anything is saved.
        client = get_llm_client("generator", settings)

        # Rulebook versions can never be deleted, so the smoke check works in a throwaway
        # database and never touches DA_DB_PATH. Cleanup errors are not ignored: if Windows
        # still had the file open, we want to hear about it.
        with TemporaryDirectory(prefix="da_smoke_") as folder:
            _run_steps(Path(folder) / "smoke_check.db", settings, client)
            # A second, empty database, so the loader in item 9 has nothing published yet.
            _run_understand_steps(Path(folder) / "smoke_understand.db", settings)
            # The same database: item 9 already published the rulebook there.
            _run_onprem_steps(Path(folder) / "smoke_understand.db", settings)
            _run_discover_steps(Path(folder) / "smoke_understand.db", settings)
            _run_reveal_step(Path(folder) / "smoke_understand.db", settings)
            _run_approach_steps(Path(folder) / "smoke_understand.db", settings)
    except (
        ConfigError,
        LLMClientError,
        RulebookError,
        DatabaseBusyError,
        UnderstandError,
        StatusMoveError,
    ) as error:
        print(f"Smoke check stopped: {error}")
        return 1

    print("Smoke check passed.")
    return 0


def _run_steps(db_path: Path, settings: Settings, client: LLMClient) -> None:
    # A request now needs a published rulebook, so v1 is published first and reported in item 5.
    seed = load_rulebook_file(SEED_RULEBOOK_FILE)
    v1 = publish_first_version(db_path, seed, SAMPLE_ADMIN, "Starter rulebook from the seed file")

    request = create_request(db_path, SAMPLE_TITLE, SAMPLE_DEVELOPER)
    print(f"2. New request created: {request.request_id} (status {request.status})")

    add_audit_event(db_path, request.request_id, "developer", "request_created")
    add_audit_event(
        db_path,
        request.request_id,
        "system",
        "smoke_check_ran",
        {"provider": settings.llm_provider},
    )
    events = list_audit_events(db_path, request.request_id)
    print(f"3. Audit events recorded for {request.request_id}: {len(events)}")
    for event in events:
        when = f"{event.timestamp:%Y-%m-%d %H:%M:%S} UTC"
        print(f"   - {when}  {event.actor}  {event.event_type}")

    reply = client.complete(SAMPLE_PROMPT)
    print(f"4. AI reply from {reply.provider} ({reply.model}): {reply.text}")

    print(f"5. Rulebook v{v1.version_number} published from the seed file by {v1.saved_by}")
    pinned = get_rulebook_for_request(db_path, request.request_id)
    print(f"6. Request {request.request_id} is pinned to v{pinned.version_number}")

    v2 = save_new_version(
        db_path,
        _with_stricter_rule(v1.rulebook, CHANGED_RULE_ID),
        v1.version_number,
        SAMPLE_ADMIN,
        f"Make {CHANGED_RULE_ID} a must fix",
    )
    pinned = get_rulebook_for_request(db_path, request.request_id)
    print(
        f"7. v{v2.version_number} saved with {CHANGED_RULE_ID} changed to must_fix; "
        f"request is still pinned to v{pinned.version_number}"
    )

    v3 = restore_version(db_path, v1.version_number, SAMPLE_ADMIN)
    listed = ", ".join(f"v{version.version_number}" for version in list_versions(db_path))
    print(
        f'8. v{v1.version_number} restored as v{v3.version_number} ("{v3.change_note}"); '
        f"versions, newest first: {listed}"
    )


def _run_understand_steps(db_path: Path, settings: Settings) -> None:
    first = load_starter_rulebook(db_path)
    second = load_starter_rulebook(db_path)
    print(f"9. Loader: {first} Second run: {second}")

    # Always the fake script, whatever the provider, so the smoke check never needs an AI.
    demo = replace(settings, llm_provider="fake", db_path=db_path)
    view = create_understand_request(demo, SAMPLE_FIRST_MESSAGE, developer_id=SAMPLE_DEVELOPER)
    request_id = view.request.request_id
    print(f"10. Request {request_id} created (status {view.request.status})")
    view = submit_form(demo, request_id, [*SAMPLE_ANSWERS, SAMPLE_REFERENCE], view.revision)
    print(f"    - 4-box form submitted: status {view.request.status}")

    decision = view.prompt
    asked_status = view.request.status
    choice = view.choices[0]
    view = choose_option(demo, request_id, choice, view.revision)
    print(
        f'11. Decision asked: "{decision}" (status {asked_status}); '
        f'chose "{choice}" (status {view.request.status})'
    )

    view = choose_option(demo, request_id, PROCEED_OPTION, view.revision)
    criteria = get_confirmed_record(db_path, request_id).acceptance_criteria
    if view.request.status != STATUS_CONFIRMED or len(criteria) != EXPECTED_CRITERIA:
        raise UnderstandError(
            f"Expected {EXPECTED_CRITERIA} criteria at {STATUS_CONFIRMED}, got {len(criteria)} "
            f"at {view.request.status}."
        )
    print(
        f"12. Confirmed as record v{view.request.version} (status {view.request.status}) "
        f"with {len(criteria)} acceptance criteria; "
        f"editing v1 was refused: {_try_to_edit_record(db_path, request_id)}"
    )


def _run_onprem_steps(db_path: Path, settings: Settings) -> None:
    """Items 13 and 14: the onprem provider against the pretend server on this computer only.

    Always the pretend server, whatever provider is set, so the smoke check never calls a real AI.
    """
    with running_fake_onprem_server() as server:
        onprem = replace(
            settings,
            llm_provider="onprem",
            onprem_url=server.url,
            onprem_model=SAMPLE_ONPREM_MODEL,
            onprem_api_key="",
            onprem_verify=True,
            db_path=db_path,
        )
        result = ping(onprem)
        if not result.ok:
            raise LLMClientError(f"The ping to the pretend server failed: {result.error}")
        print(
            f"13. Ping with onprem against the pretend server: OK in {result.seconds:.2f} seconds "
            f"(model {result.model}, server {result.host})"
        )

        view = create_understand_request(
            onprem, SAMPLE_FIRST_MESSAGE, developer_id=SAMPLE_DEVELOPER
        )
        request_id = view.request.request_id
        view = submit_form(onprem, request_id, [*SAMPLE_ANSWERS, SAMPLE_REFERENCE], view.revision)
        view = choose_option(onprem, request_id, view.choices[0], view.revision)
        view = choose_option(onprem, request_id, PROCEED_OPTION, view.revision)
    if view.request.status != STATUS_CONFIRMED:
        raise UnderstandError(f"The onprem conversation ended at {view.request.status}.")
    print(
        f"14. Conversation with onprem against the pretend server: {request_id} reached "
        f"{view.request.status} as record v{view.request.version}"
    )


def _run_discover_steps(db_path: Path, settings: Settings) -> None:
    """Items 15 to 17: Discover (Phase 3), always with the pretend index and pretend AI."""
    index = FakeSearchIndex.from_file()
    filters = SearchFilters()
    exact, _ = search_safely(index, "check upload file type", "exact", filters, 5)
    meaning, _ = search_safely(index, "parse pages", "meaning", filters, 5)
    # Open filters make the index return the flagged pieces, so our own filter has work to do.
    open_filters = SearchFilters(include_deprecated=True, include_restricted=True)
    _, dropped = search_safely(index, "legacy payroll sample settings", "exact", open_filters, 30)
    if not exact or not meaning or dropped < 3:
        raise UnderstandError("The pretend index or its safety filter did not work as expected.")
    print(
        f"15. Pretend index loaded; exact search found {exact[0].symbol}, meaning search found "
        f"{meaning[0].symbol}; the safety filter dropped {dropped} deprecated, restricted or "
        ".env-like hits"
    )

    demo = replace(settings, llm_provider="fake", db_path=db_path)
    request_id = _confirmed_request(demo)
    before = get_confirmed_record(db_path, request_id)
    view = start_discovery(demo, request_id, 0)
    found = f"{view.request.status} ({view.result.summary_source} summary)"
    view = confirm_discovery(demo, request_id, view.revision)
    if view.request.status != STATUS_DISCOVERY_CONFIRMED:
        raise UnderstandError(f"Discover ended at {view.request.status}.")
    unchanged = get_confirmed_record(db_path, request_id) == before
    print(
        f"16. {request_id}: Discover reached {found}, then {view.request.status}; "
        f"record v1 unchanged: {unchanged}"
    )

    with running_fake_onprem_server("bad-json") as server:
        bad = replace(
            demo,
            llm_provider="onprem",
            onprem_url=server.url,
            onprem_model=SAMPLE_ONPREM_MODEL,
        )
        request_id = _confirmed_request(bad)
        view = start_discovery(bad, request_id, 0)
    print(
        f"17. With the pretend server in bad-json mode, {request_id} fell back to plain results "
        f"(summary source: {view.result.summary_source}) and still reached {view.request.status}"
    )


def _run_reveal_step(db_path: Path, settings: Settings) -> None:
    """Item 18 (W5, U8): the Summary shows nothing of the form until Submit, then all the fields
    the form answered at once."""
    demo = replace(settings, llm_provider="fake", db_path=db_path)
    view = create_understand_request(demo, SAMPLE_FIRST_MESSAGE, developer_id=SAMPLE_DEVELOPER)
    before = [name for name in view.visible_fields if name not in ALWAYS_VISIBLE]
    view = submit_form(demo, view.request.request_id, [*SAMPLE_ANSWERS, ""], view.revision)
    revealed = [name for name in view.visible_fields if name not in ALWAYS_VISIBLE]
    if before or "objective" not in revealed or "inputs" not in revealed:
        raise UnderstandError(f"Before Submit {before}; after Submit {revealed}.")
    print(
        f"18. Before Submit the Summary shows no form field; after it, all {len(revealed)} at once"
    )


def _run_approach_steps(db_path: Path, settings: Settings) -> None:
    """Items 19 to 21: Approach (Phase 4) from DISCOVERY_CONFIRMED to READY_TO_BUILD, first with
    the fake provider and then with the onprem provider against the pretend server."""
    demo = replace(settings, llm_provider="fake", db_path=db_path)
    request_id = _discovery_confirmed_request(demo)
    view = _run_approach(demo, request_id)
    fake_request_id = request_id
    print(
        f"19. {request_id}: Approach with the fake provider reached {view.request.status}: "
        f"{len(view.approach.plan.files)} code files, {len(view.plan.cases)} test cases "
        f"({view.developer_case_count} yours), gate {_ticks(view)}"
    )

    with running_fake_onprem_server() as server:
        onprem = replace(
            settings,
            llm_provider="onprem",
            onprem_url=server.url,
            onprem_model=SAMPLE_ONPREM_MODEL,
            onprem_api_key="",
            onprem_verify=True,
            db_path=db_path,
        )
        request_id = _discovery_confirmed_request(demo)
        view = _run_approach(onprem, request_id)
        sent = [call["body"]["messages"][-1]["content"] for call in server.seen]
    print(
        f"20. {request_id}: Approach with onprem against the pretend server reached "
        f"{view.request.status}, gate {_ticks(view)}"
    )

    prompt = next(text for text in sent if TESTER_MARKER in text)
    planned = [item.path for item in view.approach.plan.files]
    criteria = [criterion.id for criterion in view.record.acceptance_criteria]
    if not all(name in prompt for name in criteria) or any(path in prompt for path in planned):
        raise UnderstandError("The Tester's prompt must hold the criteria and not the file plan.")
    print(
        f"21. The Tester's prompt held all {len(criteria)} criteria and none of the "
        f"{len(planned)} planned file paths"
    )
    folder = _run_workspace_steps(demo, fake_request_id)
    _run_build_steps(demo, fake_request_id, folder)


def _run_workspace_steps(settings: Settings, request_id: str) -> FakeBrowserFolder:
    """Items 22 and 23: the Workspace (Phase 5) with a pretend browser folder. It goes from
    READY_TO_BUILD to ws_ready, then a re-scan finds one file the developer changed."""
    view = workspace.get_workspace_view(settings, request_id)
    folder = _pretend_codevision_folder(view)
    facts = folder.facts(view.planned_paths, view.markers, request_id, view.max_file_kb)
    judgement = workspace.judge_facts(settings, request_id, facts, view.revision)
    if judgement.job is None:
        blocker = judgement.view.check.blockers[0]
        raise UnderstandError(f"The pretend folder was blocked: {blocker.text}")
    report = folder.run_job(judgement.job)
    view = workspace.save_check(settings, request_id, facts, report, view.revision)
    if view.step != "ws_ready" or view.request.status != STATUS_READY_TO_BUILD:
        raise UnderstandError(f"The workspace ended at {view.step}.")
    if any(path.startswith("tests/") for path in folder.files):
        raise UnderstandError("The check wrote a tests folder. It must write nothing.")
    print(
        f"22. {request_id}: workspace ready in folder {view.folder_name}: "
        f"{len([r for r in view.rows if r.baseline_at])} baselines taken, nothing written "
        "(tests stay in the app)"
    )

    edited = next(row.path for row in view.rows if row.action == "modify")
    folder.edit(edited, folder.files[edited] + "# changed by the developer\n")
    facts = folder.facts(view.planned_paths, view.markers, request_id, view.max_file_kb)
    view = workspace.rescan(settings, request_id, facts, view.revision)
    changed = [row.path for row in view.rows if row.status == "Changed by you"]
    still_ready = view.step == "ws_ready" and view.request.status == STATUS_READY_TO_BUILD
    if changed != [edited] or not still_ready:
        raise UnderstandError(f"The re-scan listed {changed}, not {[edited]}.")
    print(f"23. Re-scan found 1 file changed by the developer ({edited}); the step stays ws_ready")
    return folder


def _run_build_steps(settings: Settings, request_id: str, folder: FakeBrowserFolder) -> None:
    """Items 24 and 25: the Build + test loop (Phase 6) with the fake provider, the REAL sandbox
    (a separate Python process on the made-up reference folder) and the pretend browser folder.
    It goes from ws_ready through BUILDING to READY_FOR_REVIEW, then writes the code files."""
    view = workspace.get_workspace_view(settings, request_id)
    facts = folder.facts(view.planned_paths, view.markers, request_id, view.max_file_kb)
    build.start_build(settings, request_id, build.get_revision(settings, request_id), facts=facts)
    outcome = build_loop.run_build(settings, request_id)
    shown = tester_flow.get_build_view(settings, request_id)
    if outcome != "done" or shown.request_status != "READY_FOR_REVIEW" or shown.run is None:
        raise UnderstandError(
            f"The build ended as {outcome} at {shown.state.step}: {shown.banner_text}"
        )
    print(
        f"24. {request_id}: build {shown.run.build_number} reached READY_FOR_REVIEW "
        f"({shown.label}) in {shown.run.rounds_used} rounds, "
        f"{shown.tests_passing} frozen tests passing"
    )
    _check_tester_review(settings, request_id, shown)

    revision = build.get_revision(settings, request_id)
    job = build.prepare_write(settings, request_id, revision)
    report = folder.run_job(job)
    state = build.save_write(settings, request_id, report, revision)
    if state.step != "b_written" or any(path.startswith("tests/") for path in folder.files):
        raise UnderstandError(f"The write ended at {state.step}, or a tests folder was written.")
    print(
        f"25. {len(report.written)} code files written to the pretend folder (no tests folder); "
        f"the step is {state.step}"
    )


def _check_tester_review(settings: Settings, request_id: str, shown) -> None:
    """Item 26 (Phase 7): the build went through TESTER_REVIEW, the scripted findings are there,
    and the old Phase 6 'Layer C is not built yet' warning is gone."""
    report = shown.tester
    moves = [
        (e.details["from"], e.details["to"])
        for e in list_audit_events(settings.db_path, request_id)
        if e.event_type == "status_changed"
    ]
    if ("BUILDING", "TESTER_REVIEW") not in moves or (
        "TESTER_REVIEW",
        "READY_FOR_REVIEW",
    ) not in moves:
        raise UnderstandError("The build did not go through TESTER_REVIEW.")
    if report is None or report.review is None or not report.layer_c_ran:
        raise UnderstandError("The build has no Tester review.")
    severities = [row.finding.severity for row in report.rows]
    if severities != ["should_fix", "fyi"] or len(report.dropped) != 1:
        raise UnderstandError(f"The Tester review had {severities}, not the scripted findings.")
    said = " ".join(m.text for m in list_messages(settings.db_path, request_id))
    if "not built yet" in said or "not built yet" in shown.banner_text:
        raise UnderstandError("The old Layer C warning is still shown.")
    print(
        f"26. Tester review (round {report.review.round}, model {report.review.model}): "
        f"{len(severities)} findings kept, {len(report.dropped)} dropped, label {report.label}; "
        "the old Layer C warning is gone"
    )


def _pretend_codevision_folder(view) -> FakeBrowserFolder:
    """A made-up CodeVision clone that fits the plan: marker folders, and every file the plan
    changes with some made-up text."""
    folder = FakeBrowserFolder(name="codevision-copy")
    for marker in view.markers:
        folder.files[f"{marker}/da_pretend.py"] = "# made up\n"
    for row in view.rows:
        if row.action == "modify":
            folder.files[row.path] = "def validate(path):\n    return True\n"
        elif row.action == "create":
            folder.extra_folders.add(row.path.rsplit("/", 1)[0])
    return folder


def _run_approach(settings: Settings, request_id: str):
    """Proceed, answer the design choice by its first button, accept both, add one case."""
    view = approach.start_approach(settings, request_id, 0)
    view = approach.choose_design_option(settings, request_id, view.buttons[0][1], view.revision)
    view = approach.accept_approach(settings, request_id, view.revision)
    view = approach.submit_text(settings, request_id, SAMPLE_CASE, view.revision)
    view = approach.keep_case(settings, request_id, view.revision)
    view = approach.accept_test_plan(settings, request_id, view.revision)
    if view.request.status != STATUS_READY_TO_BUILD:
        raise UnderstandError(f"Approach ended at {view.request.status}.")
    return view


def _discovery_confirmed_request(settings: Settings) -> str:
    request_id = _confirmed_request(settings)
    view = start_discovery(settings, request_id, 0)
    view = confirm_discovery(settings, request_id, view.revision)
    if view.request.status != STATUS_DISCOVERY_CONFIRMED:
        raise UnderstandError(f"Discover ended at {view.request.status}.")
    return request_id


def _ticks(view) -> str:
    return " ".join("yes" if check.passed else "no" for check in view.gate)


def _confirmed_request(settings: Settings) -> str:
    view = create_understand_request(settings, SAMPLE_FIRST_MESSAGE, developer_id=SAMPLE_DEVELOPER)
    request_id = view.request.request_id
    view = submit_form(settings, request_id, [*SAMPLE_ANSWERS, SAMPLE_REFERENCE], view.revision)
    view = choose_option(settings, request_id, view.choices[0], view.revision)
    view = choose_option(settings, request_id, PROCEED_OPTION, view.revision)
    if view.request.status != STATUS_CONFIRMED:
        raise UnderstandError(f"The conversation ended at {view.request.status}.")
    return request_id


def _try_to_edit_record(db_path: Path, request_id: str) -> str:
    """Try to change confirmed record v1 with raw SQL. The database must refuse it (rule R5)."""
    try:
        with open_db(db_path) as conn:
            conn.execute(
                "UPDATE da_request_records SET record = '{}' WHERE request_id = ?", (request_id,)
            )
    except sqlite3.IntegrityError as error:
        return str(error)
    raise UnderstandError("Record v1 could be edited. The append-only protection is missing.")


def _with_stricter_rule(rulebook: Rulebook, rule_id: str) -> Rulebook:
    rules = [
        rule.model_copy(update={"severity": "must_fix"}) if rule.rule_id == rule_id else rule
        for rule in rulebook.rules
    ]
    return rulebook.model_copy(update={"rules": rules})


def main(env_file: Path | None = DEFAULT_ENV_FILE) -> int:
    try:
        settings = load_settings(env_file=env_file)
    except ConfigError as error:
        print(f"Smoke check stopped: {error}")
        return 1
    return run_smoke_check(settings)


if __name__ == "__main__":
    sys.exit(main())
