import subprocess
import sys
from pathlib import Path

import chief_tick
import pytest
import status

ROOT = Path(__file__).resolve().parents[2]


def _make(tmp_path, log_lines=0):
    f = tmp_path / "STATUS.md"
    lines = ["# STATUS", "Usage: x", "## Log"] + [f"- old {i}" for i in range(log_lines)]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


def test_repo_status_file_is_within_60_lines_and_has_the_usage_line():
    text = (ROOT / "STATUS.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 60
    assert "Usage:" in text
    for fact in ("Phases 0 to 6", "auto/phase-7", "needs-work-test", "Q7", "Q9", "Q15",
                 "P26", "P27", "P28"):
        assert fact in text


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


# ---- Phase A fix 3, F2: set_next and the `next` command ----

def _next_lines(path):
    return [x for x in path.read_text(encoding="utf-8").splitlines()
            if x.lstrip("- ").startswith("Next:")]


def _status(tmp_path, body):
    path = tmp_path / "STATUS.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_as5_next_replaces_the_line_and_its_continuation_lines(tmp_path):
    path = _status(tmp_path, "# S\n## Where we are\n- a\n- Next: old\n  more old\n- b\n## Log\n")
    status.set_next(path, "builder continue Phase 8 from step 10")
    assert path.read_text(encoding="utf-8") == (
        "# S\n## Where we are\n- a\n- Next: builder continue Phase 8 from step 10\n- b\n## Log\n")


def test_next_removes_a_second_next_line(tmp_path):
    path = _status(tmp_path, "## Where we are\n- Next: a\n- x\n- Next: b\n  tail\n## Log\n")
    status.set_next(path, "c")
    assert _next_lines(path) == ["- Next: c"]
    assert "tail" not in path.read_text(encoding="utf-8")


def test_next_is_added_under_where_we_are_when_missing(tmp_path):
    path = _status(tmp_path, "# S\n## Where we are\n- a\n\n## Other\n- z\n## Log\n- 1\n")
    status.set_next(path, "go")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[lines.index("## Where we are") + 1:][:3] == ["- a", "- Next: go", ""]


def test_next_creates_the_heading_before_the_log_when_it_is_missing(tmp_path):
    path = _status(tmp_path, "# S\nUsage: x\n## Log\n- 1\n")
    status.set_next(path, "go")
    assert path.read_text(encoding="utf-8") == (
        "# S\nUsage: x\n## Where we are\n- Next: go\n\n## Log\n- 1\n")


def test_as6_empty_text_is_refused_and_the_file_is_unchanged(tmp_path):
    path = _status(tmp_path, "## Where we are\n- Next: keep me\n## Log\n")
    for bad in ("", "   ", "\n"):
        with pytest.raises(ValueError):
            status.set_next(path, bad)
    assert path.read_text(encoding="utf-8") == "## Where we are\n- Next: keep me\n## Log\n"


def test_next_collapses_line_breaks_into_one_line(tmp_path):
    path = _status(tmp_path, "## Where we are\n- Next: a\n## Log\n")
    status.set_next(path, "one\ntwo")
    assert _next_lines(path) == ["- Next: one two"]


def test_as5_a_full_file_stays_at_60_lines_or_fewer(tmp_path):
    body = "## Where we are\n- Next: a\n## Log\n" + "".join(f"- log {n}\n" for n in range(57))
    path = _status(tmp_path, body)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 60
    status.set_next(path, "builder continue Phase 8 from step 10")
    assert len(path.read_text(encoding="utf-8").splitlines()) <= 60
    assert _next_lines(path) == ["- Next: builder continue Phase 8 from step 10"]


def test_as5_the_next_command_changes_the_status_file(tmp_path, capsys):
    # the shared fixture points chief_tick.STATUS_FILE at a temp STATUS.md
    assert chief_tick.main(["next", "builder continue Phase 8 from step 10"]) == 0
    assert "builder continue Phase 8 from step 10" in capsys.readouterr().out
    assert _next_lines(chief_tick.STATUS_FILE) == ["- Next: builder continue Phase 8 from step 10"]


def test_as6_the_next_command_refuses_empty_text(tmp_path, capsys):
    before = chief_tick.STATUS_FILE.read_text(encoding="utf-8")
    assert chief_tick.main(["next", ""]) == 1
    assert "Refused" in capsys.readouterr().err
    assert chief_tick.STATUS_FILE.read_text(encoding="utf-8") == before
