"""Proves Phases 0 and 1 work end to end. Run: .venv\\Scripts\\python src\\da_smoke_check.py"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.da_llm_client import LLMClient, LLMClientError, get_llm_client
from configs.da_config import DEFAULT_ENV_FILE, ConfigError, Settings, load_settings
from db_table_functions.da_db import DatabaseBusyError
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
from pydantic_classes.da_rulebook_models import Rulebook

SAMPLE_TITLE = "Smoke check: sample change to a made-up loan program"
SAMPLE_DEVELOPER = "dev-0001"
SAMPLE_ADMIN = "admin-0001"
SAMPLE_PROMPT = "Say hello to the Developer Assistant team in one sentence."
CHANGED_RULE_ID = "CV-PY-002"


def run_smoke_check(settings: Settings) -> int:
    """Print the Phase 0 and Phase 1 checks. Return 0 if all passed, 1 if one stopped."""
    print(f"1. Active AI provider: {settings.llm_provider}")
    try:
        # Set up the AI client first, so a setup problem stops us before anything is saved.
        client = get_llm_client("generator", settings)

        # Rulebook versions can never be deleted, so the smoke check works in a throwaway
        # database and never touches DA_DB_PATH. Cleanup errors are not ignored: if Windows
        # still had the file open, we want to hear about it.
        with TemporaryDirectory(prefix="da_smoke_") as folder:
            _run_steps(Path(folder) / "smoke_check.db", settings, client)
    except (ConfigError, LLMClientError, RulebookError, DatabaseBusyError) as error:
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
