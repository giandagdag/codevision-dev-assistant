"""One-time setup: publish the starter rulebook as v1 (spec 3.7).

Run: .venv\\Scripts\\python src\\da_load_starter_rulebook.py
Safe to run again: if any version exists, it changes nothing.
"""

import json
import sys
from pathlib import Path

from configs.da_config import DEFAULT_ENV_FILE, ConfigError, load_settings
from db_table_functions.da_db import DatabaseBusyError
from db_table_functions.db_tbl_da_rulebook import (
    SEED_RULEBOOK_FILE,
    RulebookError,
    get_active_version,
    load_rulebook_file,
    publish_first_version,
    save_new_version,
)
from pydantic_classes.da_rulebook_models import Rulebook

SAVED_BY = "setup-script"
CHANGE_NOTE = "Starter rulebook from the seed file"


WORK_PURPOSE_FILE = SEED_RULEBOOK_FILE.with_name("da_rulebook_seed_work.json")
HOME_APP_NAME = "Harbour Loans"
REFRESH_NOTE = "Purpose and scope now describe CodeVision"


def _work_purpose() -> dict:
    return json.loads(WORK_PURPOSE_FILE.read_text(encoding="utf-8"))


def _with_work_purpose(rulebook: Rulebook) -> Rulebook:
    charter = rulebook.charter.model_copy(update=_work_purpose())
    return rulebook.model_copy(update={"charter": charter})


def load_starter_rulebook(db_path: Path, at_work: bool = False) -> str:
    """Publish the seed as v1 if no version exists yet. Returns the line to print."""
    active = get_active_version(db_path)
    if active is not None:
        return f"Rulebook already published (active v{active.version_number}). Nothing changed."
    seed = load_rulebook_file(SEED_RULEBOOK_FILE)
    if at_work:
        seed = _with_work_purpose(seed)
    # publish_first_version refuses if another run published in the meantime.
    version = publish_first_version(db_path, seed, SAVED_BY, CHANGE_NOTE)
    return f"Rulebook v{version.version_number} published."


def refresh_purpose(db_path: Path) -> str:
    """Save a new version whose purpose and scope describe CodeVision (old one stays restorable)."""
    active = get_active_version(db_path)
    if active is None:
        return "No rulebook is published yet. Run the loader without options first."
    charter = active.rulebook.charter
    if HOME_APP_NAME not in " ".join([charter.purpose, *charter.in_scope]):
        return "Nothing to change."
    version = save_new_version(
        db_path,
        _with_work_purpose(active.rulebook),
        active.version_number,
        SAVED_BY,
        REFRESH_NOTE,
    )
    return f"Rulebook v{version.version_number} saved. Restore v{active.version_number} to undo."


def main(
    env_file: Path | None = DEFAULT_ENV_FILE, argv: list[str] | None = None
) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        settings = load_settings(env_file=env_file)
        at_work = settings.llm_provider == "onprem"  # spec D-B: this is how we know
        if "--refresh-purpose" in argv:
            if not at_work:
                print("Loader stopped: --refresh-purpose only runs at work (onprem).")
                return 1
            print(refresh_purpose(settings.db_path))
        else:
            print(load_starter_rulebook(settings.db_path, at_work))
    except (ConfigError, RulebookError, DatabaseBusyError) as error:
        print(f"Loader stopped: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
