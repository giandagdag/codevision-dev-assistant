"""The made-up SonarQube sample list shown on the Coding standards tab (Phase 11b, spec section 7).

Read only. The real list comes from SonarQube when access is decided (work fact WF-4). Plain code,
no AI.
"""

import json
from datetime import datetime
from pathlib import Path

from agents.da_admin_index import index_dir
from agents.da_sonar_client import SonarError, fetch_active_rules
from configs.da_config import Settings

SAMPLE_FILE = Path(__file__).resolve().parents[1] / "data" / "da_sonar_checks_sample.json"
SAMPLE_BANNER = (
    "Sample list. The real list comes from SonarQube when access is decided (WF-4)."
)


def load_sonar_sample(path: Path = SAMPLE_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


SNAPSHOT_NAME = "da_sonar_rules.json"


def snapshot_path(directory: Path | None = None) -> Path:
    return (directory or index_dir()) / SNAPSHOT_NAME


def load_snapshot(directory: Path | None = None) -> dict | None:
    """The saved SonarQube list (profile, fetched_at, rules), or None when there is none."""
    try:
        return json.loads(snapshot_path(directory).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def refresh_snapshot(settings: Settings, directory: Path | None = None, session=None) -> str:
    """Fetch and save the list. Returns a plain message; on any error the old file stays."""
    try:
        profile, rules = fetch_active_rules(settings, session)
    except SonarError as error:
        return str(error)
    target = snapshot_path(directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    body = {"profile": profile, "fetched_at": stamp, "rules": rules}
    target.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return f"Saved {len(rules)} rules from SonarQube."


def source_pill(snapshot: dict | None) -> str:
    if snapshot is None:
        return "Sample list"
    return f"From SonarQube, {snapshot['fetched_at'][:10]}"


def sample_with_mapping(
    severity_map: dict[str, str], sample: list[dict] | None = None
) -> list[dict]:
    """Each check with its mapped severity (key, name, sonar, mapped). Real list beats sample."""
    if sample is None:
        snapshot = load_snapshot()
        sample = snapshot["rules"] if snapshot else None
    checks = load_sonar_sample() if sample is None else sample
    return [
        {
            "key": check["key"],
            "name": check["name"],
            "sonar": check["severity"],
            "mapped": severity_map.get(check["severity"], ""),
        }
        for check in checks
    ]
