"""The made-up SonarQube sample list shown on the Coding standards tab (Phase 11b, spec section 7).

Read only. The real list comes from SonarQube when access is decided (work fact WF-4). Plain code,
no AI.
"""

import json
from pathlib import Path

SAMPLE_FILE = Path(__file__).resolve().parents[1] / "data" / "da_sonar_checks_sample.json"
SAMPLE_BANNER = (
    "Sample list. The real list comes from SonarQube when access is decided (WF-4)."
)


def load_sonar_sample(path: Path = SAMPLE_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def sample_with_mapping(
    severity_map: dict[str, str], sample: list[dict] | None = None
) -> list[dict]:
    """Each sample check with its mapped severity (key, name, sonar, mapped)."""
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
