"""A local log of interpreter replies the engine rejected (spec 2.3, decision D-D).

Like a job log you read after a failure: it keeps the raw text the AI sent, so a wrong shape can
be seen and fixed quickly. The file stays on the laptop (logs/ is ignored by Git). It must never
stop the conversation, so a write problem is only a warning.
"""

from datetime import UTC, datetime
from pathlib import Path

from configs.da_config import PROJECT_ROOT
from da_logging import get_logger
from db_table_functions.db_tbl_da_requests import SINGAPORE_TIME

logger = get_logger(__name__)

LOG_FILE = PROJECT_ROOT / "logs" / "da_rejected_replies.log"
# A very long reply is cut so one entry cannot fill the disk.
RAW_TEXT_LIMIT = 20_000


def write_rejected_reply(
    request_id: str,
    attempt: int,
    provider: str,
    model: str,
    problems: list[str],
    raw_text: str,
    now: datetime | None = None,
    log_file: Path | None = None,
    step: str = "understand",
) -> None:
    """Add one entry to the log. Never raises. step says which engine the reply came from."""
    when = (now or datetime.now(UTC)).astimezone(SINGAPORE_TIME)
    shown_text = raw_text[:RAW_TEXT_LIMIT]
    cut_note = f", cut at {RAW_TEXT_LIMIT}" if len(raw_text) > RAW_TEXT_LIMIT else ""
    problem_lines = "\n".join(f"- {problem}" for problem in problems) or "- (none listed)"
    entry = (
        f"=== {when:%Y-%m-%d %H:%M:%S} SGT | request {request_id or '(none)'} | "
        f"step {step} | attempt {attempt} | provider {provider} | model {model or '(unknown)'}\n"
        f"Problems:\n{problem_lines}\n"
        f"Raw reply ({len(raw_text)} characters{cut_note}):\n{shown_text}\n"
        "=== end ===\n"
    )
    path = log_file or LOG_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
    except (OSError, ValueError) as error:  # ValueError: text that cannot be encoded
        logger.warning(
            "Could not write the rejected-reply log (%s). Carrying on.", type(error).__name__
        )
