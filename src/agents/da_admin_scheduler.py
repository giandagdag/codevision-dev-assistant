"""Nightly refresh (fix 11-3, D-D). Plain code, no AI.

AS400 picture: a job schedule entry. Once a minute a small thread looks at the clock; when the
Admin-set time (Singapore time) has passed and today has not run yet, it submits one Delta job.
The job takes the same lock file as a manual one, so a second server process loses.
It only runs while the DA server is running (no catch-up after a restart).
"""

import threading
import time
from datetime import UTC, date, datetime

from agents.da_admin_rebuild import start_rebuild
from configs.da_config import Settings
from da_logging import get_logger
from db_table_functions.db_tbl_da_requests import SINGAPORE_TIME
from db_table_functions.db_tbl_da_rulebook import get_active_version
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)

CHECK_EVERY_SECONDS = 60
NIGHTLY_USER = "nightly"


def sgt(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)).astimezone(SINGAPORE_TIME)


def is_due(policy: Policy, now: datetime, last_day: date | None) -> bool:
    """Nightly is on, the set time has passed in Singapore, and today has not run yet."""
    if policy.index_refresh_mode != "nightly":
        return False
    local = sgt(now)
    return local.strftime("%H:%M") >= policy.index_nightly_time and local.date() != last_day


def tick(settings: Settings, now: datetime | None, last_day: date | None, start=start_rebuild):
    """One look at the clock. Returns the day to remember (set when a job was tried, so a lost lock
    or a failed job is not retried every minute)."""
    now = now or datetime.now(UTC)
    version = get_active_version(settings.db_path)
    if version is None or not is_due(version.rulebook.policy, now, last_day):
        return last_day
    started, message = start(
        version.rulebook.policy, NIGHTLY_USER, mode="delta", trigger="Nightly",
        provider=settings.llm_provider, settings=settings,
    )  # fmt: skip
    logger.info("Nightly refresh: %s", message if not started else "started")
    return sgt(now).date()


def start_scheduler(settings: Settings) -> threading.Thread:
    """Daemon thread. A server started after the set time waits for tomorrow's."""
    state = {"day": sgt().date()}

    def loop() -> None:
        while True:
            time.sleep(CHECK_EVERY_SECONDS)
            try:
                state["day"] = tick(settings, None, state["day"])
            except Exception as error:  # the clock thread must never die
                logger.warning("Nightly check failed: %s", type(error).__name__)

    thread = threading.Thread(target=loop, daemon=True, name="da-nightly")
    thread.start()
    return thread
