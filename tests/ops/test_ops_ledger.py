import csv
import json

import ledger

NOW = 1_800_000_000.0


def rows(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_two_runs_give_two_lines_and_one_header(tmp_path):
    f = tmp_path / "logs" / "usage-ledger.csv"
    ledger.add_line({"phase": "7", "stage": "spec", "model": "opus", "outcome": "ok"}, f, NOW)
    ledger.add_line({"phase": "7", "stage": "plan", "model": "sonnet", "outcome": "ok"}, f, NOW)
    text = f.read_text(encoding="utf-8").splitlines()
    assert len(text) == 3 and text[0].split(",") == ledger.COLUMNS
    assert [r["stage"] for r in rows(f)] == ["spec", "plan"]


def test_a_failed_run_still_gets_a_line_and_blanks_stay_blank(tmp_path):
    f = tmp_path / "l.csv"
    ledger.add_line({"phase": "7", "stage": "build", "outcome": "failed: guard stop"}, f, NOW)
    row = rows(f)[0]
    assert row["outcome"] == "failed: guard stop"
    assert row["input_tokens"] == "" and row["cost_usd"] == ""
    assert row["time_sgt"].endswith("SGT")


def test_tokens_are_read_from_claude_json_and_missing_is_blank():
    text = json.dumps({"result": "x", "total_cost_usd": 0.12,
                       "usage": {"input_tokens": 100, "output_tokens": 20}})
    assert ledger.tokens_from_result(text) == {
        "input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": None,
        "cache_creation_input_tokens": None, "cost_usd": 0.12}
    assert ledger.tokens_from_result("not json") == {}
    assert ledger.tokens_from_result("[1]") == {}
    assert ledger.tokens_from_result('{"result": "x"}')["input_tokens"] is None


def test_unknown_keys_are_ignored_and_commas_are_safe(tmp_path):
    f = tmp_path / "l.csv"
    ledger.add_line({"stage": "a, b", "secret": "nope", "outcome": "ok"}, f, NOW)
    assert rows(f)[0]["stage"] == "a, b"
    assert "nope" not in f.read_text(encoding="utf-8")


def test_the_default_path_is_under_logs_which_git_ignores():
    assert ledger.ledger_path().parts[-2:] == ("logs", "usage-ledger.csv")


def test_cache_tokens_have_their_own_columns_and_are_read_from_the_usage_block(tmp_path):
    reply = json.dumps({"total_cost_usd": 0.04, "usage": {
        "input_tokens": 4, "output_tokens": 349, "cache_read_input_tokens": 12000,
        "cache_creation_input_tokens": 3000}})
    assert "cache_read_input_tokens" in ledger.COLUMNS
    assert "cache_creation_input_tokens" in ledger.COLUMNS
    f = tmp_path / "l.csv"
    ledger.add_line({"stage": "a", **ledger.tokens_from_result(reply)}, f, NOW)
    row = rows(f)[0]
    assert (row["input_tokens"], row["cache_read_input_tokens"],
            row["cache_creation_input_tokens"], row["output_tokens"]) == (
        "4", "12000", "3000", "349")


def test_an_old_ledger_with_the_old_header_is_set_aside_not_mixed_up(tmp_path):
    f = tmp_path / "l.csv"
    f.write_text("time_sgt,phase,stage\n1,2,3\n", encoding="utf-8")
    ledger.add_line({"stage": "new", "outcome": "ok"}, f, NOW)
    assert [r["stage"] for r in rows(f)] == ["new"]
    old = list(tmp_path.glob("l.old-*.csv"))
    assert len(old) == 1 and "1,2,3" in old[0].read_text(encoding="utf-8")
    ledger.add_line({"stage": "again"}, f, NOW)
    assert len(rows(f)) == 2 and len(list(tmp_path.glob("l.old-*.csv"))) == 1
