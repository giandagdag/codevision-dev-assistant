import subprocess
import sys
from pathlib import Path

import status

ROOT = Path(__file__).resolve().parents[2]


def _make(tmp_path, log_lines=0):
    f = tmp_path / "STATUS.md"
    lines = ["# STATUS", "Usage: x", "## Log"] + [f"- old {i}" for i in range(log_lines)]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


def test_status_file_shape_is_within_60_lines_and_has_the_usage_line(tmp_path):
    # A test copy, not the real STATUS.md: the chief rewrites that file every tick.
    f = _make(tmp_path, log_lines=40)
    status.set_usage_line(f, 5, 39, "8 Nov 12:51 SGT", stopped=False)
    status.add_log(f, "one more")
    text = f.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 60
    assert text.count("Usage:") == 1


def test_log_is_trimmed_oldest_first_to_60_lines(tmp_path):
    f = _make(tmp_path, log_lines=70)
    status.add_log(f, "newest")
    lines = f.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 60
    assert lines[-1] == "- newest"
    assert "- old 0" not in lines  # oldest gone
    assert lines[:3] == ["# STATUS", "Usage: x", "## Log"]  # top part kept


def test_usage_line_is_replaced_not_duplicated(tmp_path):
    f = _make(tmp_path)
    status.set_usage_line(f, 12, 81.5, "6 Nov 14:05 SGT", stopped=True)
    status.set_usage_line(f, 13, 82, "6 Nov 14:35 SGT", stopped=True)
    text = f.read_text(encoding="utf-8")
    assert text.count("Usage:") == 1
    assert "Usage: 5h 13% / weekly 82% (as of 6 Nov 14:35 SGT), stopped yes" in text


def test_usage_line_with_unknown_numbers(tmp_path):
    f = _make(tmp_path)
    status.set_usage_line(f, None, None, "now", stopped=True)
    assert "5h unknown / weekly unknown" in f.read_text(encoding="utf-8")


def test_mark_paused_writes_a_log_line(tmp_path):
    f = _make(tmp_path)
    status.mark_paused(f, "spec D-C", "issue #12")
    assert "PAUSED spec D-C: waiting for Gian, see issue #12" in f.read_text(encoding="utf-8")


def test_claude_md_is_under_the_size_budget_and_has_the_auto_branch_rule():
    raw = (ROOT / "CLAUDE.md").read_bytes()
    assert len(raw) <= 6000
    text = raw.decode("utf-8")
    assert "auto/phase-N" in text and "auto/phases-7-10" in text
    assert "only the chief merges" in text
    assert "ops/quiet.py" in text


def test_workers_get_an_empty_mcp_file():
    import json

    data = json.loads((ROOT / ".claude" / "mcp-empty.json").read_text(encoding="utf-8"))
    assert data == {"mcpServers": {}}


def test_script_prints_line_count(tmp_path):
    f = _make(tmp_path)
    out = subprocess.run([sys.executable, str(ROOT / "ops" / "status.py"), str(f)],
                         capture_output=True, text=True).stdout
    assert out.strip() == "3 lines"
