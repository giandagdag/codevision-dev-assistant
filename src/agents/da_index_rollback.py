"""Roll the index back to a saved build (Upgrade G, G5d). Plain code, no AI.

AS400 picture: RSTOBJ from a save file. Takes the same job lock as a rebuild, so nothing else
writes the index files while they are put back.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

from agents.da_admin_audit import INDEX_ROLLED_BACK, add_admin_event
from agents.da_admin_index import record_run
from agents.da_admin_rebuild import _lock_path, _take_lock, running_since
from agents.da_index_builds import COPY_NAMES, builds_dir, has_copy

BUSY = "A rebuild or tag job is running. Wait for it to finish."


def roll_back(out: Path, number: int, who: str, now: datetime | None = None) -> tuple[bool, str]:
    """Put build `number`'s index files back. Needs a saved copy and no running job. Newer copies
    and all manifests stay."""
    if not has_copy(out, number):
        return False, f"Build {number} has no saved copy, so it cannot be used."
    started = now or datetime.now()
    if running_since(started, out) is not None or not _take_lock(started, out):
        return False, BUSY
    try:
        sides = [(out / (name + ".new"), out / name) for name in COPY_NAMES]
        try:  # copy everything first: a failed copy leaves the current index as it was
            for (side, _), name in zip(sides, COPY_NAMES, strict=True):
                shutil.copy2(builds_dir(out) / str(number) / name, side)
        except OSError as error:
            for side, _ in sides:
                side.unlink(missing_ok=True)
            return False, (
                f"Build {number} could not be put back ({error}). The current index is unchanged."
            )
        try:
            for side, target in sides:
                os.replace(side, target)
        except OSError as error:  # rare (a locked file): say plainly that the files may be mixed
            for side, _ in sides:
                side.unlink(missing_ok=True)
            record_run(who, started, False, 0, [], f"Roll back to build {number} failed", out, {})
            return False, (
                f"Build {number} was only partly put back ({error}). "
                "Run a full rebuild to make the index consistent."
            )
        text = f"Rolled back to build {number}"
        add_admin_event(INDEX_ROLLED_BACK, who, text, out, started)
        record_run(who, started, True, 0, [], text, out, {"rolled_back_to": number})
    finally:
        _lock_path(out).unlink(missing_ok=True)
    return True, text
