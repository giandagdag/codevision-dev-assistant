"""Proves Phase 0 works end to end. Run: .venv\\Scripts\\python src\\da_smoke_check.py"""

import sys
from pathlib import Path

from agents.da_llm_client import LLMClientError, get_llm_client
from configs.da_config import DEFAULT_ENV_FILE, ConfigError, Settings, load_settings
from db_table_functions.db_tbl_da_audit import add_audit_event, list_audit_events
from db_table_functions.db_tbl_da_requests import create_request

SAMPLE_TITLE = "Smoke check: sample change to a made-up loan program"
SAMPLE_DEVELOPER = "dev-0001"
SAMPLE_PROMPT = "Say hello to the Developer Assistant team in one sentence."


def run_smoke_check(settings: Settings) -> int:
    """Print the four Phase 0 checks. Return 0 if all passed, 1 if one stopped with a message."""
    print(f"1. Active AI provider: {settings.llm_provider}")
    try:
        # Set up the AI client first, so a setup problem stops us before anything is saved.
        client = get_llm_client("generator", settings)

        request = create_request(settings.db_path, SAMPLE_TITLE, SAMPLE_DEVELOPER)
        print(f"2. New request created: {request.request_id} (status {request.status})")

        add_audit_event(settings.db_path, request.request_id, "developer", "request_created")
        add_audit_event(
            settings.db_path,
            request.request_id,
            "system",
            "smoke_check_ran",
            {"provider": settings.llm_provider},
        )
        events = list_audit_events(settings.db_path, request.request_id)
        print(f"3. Audit events recorded for {request.request_id}: {len(events)}")
        for event in events:
            when = f"{event.timestamp:%Y-%m-%d %H:%M:%S} UTC"
            print(f"   - {when}  {event.actor}  {event.event_type}")

        reply = client.complete(SAMPLE_PROMPT)
        print(f"4. AI reply from {reply.provider} ({reply.model}): {reply.text}")
    except (ConfigError, LLMClientError) as error:
        print(f"Smoke check stopped: {error}")
        return 1

    print("Smoke check passed.")
    return 0


def main(env_file: Path | None = DEFAULT_ENV_FILE) -> int:
    try:
        settings = load_settings(env_file=env_file)
    except ConfigError as error:
        print(f"Smoke check stopped: {error}")
        return 1
    return run_smoke_check(settings)


if __name__ == "__main__":
    sys.exit(main())
