"""One-time setup: publish the starter rulebook as v1 (spec 3.7).

Run: .venv\\Scripts\\python src\\da_load_starter_rulebook.py
Safe to run again: if any version exists, it changes nothing.
"""

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
)

SAVED_BY = "setup-script"
CHANGE_NOTE = "Starter rulebook from the seed file"


def load_starter_rulebook(db_path: Path) -> str:
    """Publish the seed as v1 if no version exists yet. Returns the line to print."""
    active = get_active_version(db_path)
    if active is not None:
        return f"Rulebook already published (active v{active.version_number}). Nothing changed."
    # publish_first_version refuses if another run published in the meantime.
    version = publish_first_version(
        db_path, load_rulebook_file(SEED_RULEBOOK_FILE), SAVED_BY, CHANGE_NOTE
    )
    return f"Rulebook v{version.version_number} published."


def main(env_file: Path | None = DEFAULT_ENV_FILE) -> int:
    try:
        settings = load_settings(env_file=env_file)
        print(load_starter_rulebook(settings.db_path))
    except (ConfigError, RulebookError, DatabaseBusyError) as error:
        print(f"Loader stopped: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
