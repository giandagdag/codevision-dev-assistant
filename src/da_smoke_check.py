"""Proves Phases 0, 1, 2A, 2C and 3 work end to end.

Run: .venv\\Scripts\\python src\\da_smoke_check.py
"""

import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.da_discover_flow import confirm_discovery, start_discovery
from agents.da_llm_client import LLMClient, LLMClientError, get_llm_client
from agents.da_search_index import FakeSearchIndex, search_safely
from agents.da_understand_flow import (
    PROCEED_OPTION,
    choose_option,
    create_understand_request,
    submit_answer,
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
from db_table_functions.db_tbl_da_understand import UnderstandError, get_confirmed_record
from pydantic_classes.da_discovery_models import SearchFilters
from pydantic_classes.da_models import STATUS_CONFIRMED, STATUS_DISCOVERY_CONFIRMED, StatusMoveError
from pydantic_classes.da_rulebook_models import Rulebook
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
    for number, answer in enumerate(SAMPLE_ANSWERS, start=1):
        view = submit_answer(demo, request_id, answer, view.revision)
        print(f"    - Question {number} answered: status {view.request.status}")

    decision = view.prompt
    asked_status = view.request.status
    choice = view.choices[0]
    view = choose_option(demo, request_id, choice, view.revision)
    print(
        f'11. Decision asked: "{decision}" (status {asked_status}); '
        f'chose "{choice}" (status {view.request.status})'
    )

    view = submit_answer(demo, request_id, SAMPLE_REFERENCE, view.revision)
    view = choose_option(demo, request_id, PROCEED_OPTION, view.revision)
    print(
        f"12. Confirmed as record v{view.request.version} (status {view.request.status}); "
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
        for answer in SAMPLE_ANSWERS:
            view = submit_answer(onprem, request_id, answer, view.revision)
        view = choose_option(onprem, request_id, view.choices[0], view.revision)
        view = submit_answer(onprem, request_id, SAMPLE_REFERENCE, view.revision)
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


def _confirmed_request(settings: Settings) -> str:
    view = create_understand_request(
        settings, SAMPLE_FIRST_MESSAGE, developer_id=SAMPLE_DEVELOPER
    )
    request_id = view.request.request_id
    for answer in SAMPLE_ANSWERS:
        view = submit_answer(settings, request_id, answer, view.revision)
    view = choose_option(settings, request_id, view.choices[0], view.revision)
    view = submit_answer(settings, request_id, SAMPLE_REFERENCE, view.revision)
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
