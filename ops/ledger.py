"""Token ledger (A5): one line per worker run in `logs/usage-ledger.csv`.

AS400 comparison: the job log line written when each job ends, good or bad.
The file stays on the laptop (`logs/` is ignored by Git). Missing numbers are left blank,
never invented. Token field names follow the Agent SDK names (confirmed at A-P1).
NOTE: `input_tokens` counts only the UNCACHED input. The real input is
input_tokens + cache_read_input_tokens + cache_creation_input_tokens (A-P1 saw input_tokens=4).
"""

import csv
import json
import os
import time
from pathlib import Path

import usage_guard

ROOT = Path(__file__).resolve().parent.parent
COLUMNS = [
    "time_sgt", "phase", "stage", "model",
    "five_hour_before", "five_hour_after", "weekly_before", "weekly_after",
    "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
    "cost_usd", "outcome",
]


def ledger_path() -> Path:
    return Path(os.environ.get("DA_LEDGER_FILE", ROOT / "logs" / "usage-ledger.csv"))


def tokens_from_result(text: str) -> dict:
    """Read tokens and cost from `claude -p --output-format json` output. Blank if absent."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "cost_usd": data.get("total_cost_usd"),
    }


def add_line(row: dict, path: Path | None = None, now: float | None = None) -> None:
    """Append one line. The header is written once. Unknown keys are ignored."""
    path = path or ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {**row, "time_sgt": usage_guard.format_sgt(time.time() if now is None else now)}
    _set_aside_old_header(path, now)
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow({c: ("" if row.get(c) is None else row[c]) for c in COLUMNS})



def _set_aside_old_header(path: Path, now: float | None) -> None:
    """A ledger written with an older column list would mix up the new rows: rename it."""
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle), [])
    if header != COLUMNS:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time() if now is None else now))
        path.rename(path.with_name(f"{path.stem}.old-{stamp}{path.suffix}"))
