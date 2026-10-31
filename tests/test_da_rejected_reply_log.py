"""The rejected-reply log (Phase 2C, spec 2.3)."""

from datetime import UTC, datetime

from agents import da_rejected_reply_log
from agents.da_rejected_reply_log import RAW_TEXT_LIMIT, write_rejected_reply
from agents.da_understand_agent import interpret
from pydantic_classes.da_request_record_models import RequestRecord
from tests.da_stub_client import StubClient, stub_reply

WHEN = datetime(2026, 10, 30, 16, 5, 9, tzinfo=UTC)  # 00:05:09 next day in Singapore


def entry(log_file, **changes):
    values = {
        "request_id": "CVDA-2026-0001",
        "attempt": 1,
        "provider": "onprem",
        "model": "test-qwen",
        "problems": ["The reply was not valid JSON. Reply with JSON only."],
        "raw_text": "this is not json",
        "now": WHEN,
        "log_file": log_file,
    }
    values.update(changes)
    write_rejected_reply(**values)
    return log_file.read_text(encoding="utf-8")


def test_entry_holds_time_id_attempt_provider_model_problems_and_raw_text(tmp_path):
    text = entry(tmp_path / "logs" / "rejected.log")

    assert "2026-10-31 00:05:09 SGT" in text  # Singapore time, not UTC
    assert "request CVDA-2026-0001" in text
    assert "attempt 1" in text
    assert "provider onprem" in text
    assert "model test-qwen" in text
    assert "- The reply was not valid JSON. Reply with JSON only." in text
    assert "this is not json" in text


def test_entries_are_added_not_replaced(tmp_path):
    log_file = tmp_path / "rejected.log"
    entry(log_file, attempt=1)
    text = entry(log_file, attempt=2)

    assert text.count("=== 2026") == 2
    assert "attempt 1" in text and "attempt 2" in text


def test_long_raw_text_is_cut_at_20000_characters(tmp_path):
    text = entry(tmp_path / "rejected.log", raw_text="a" * (RAW_TEXT_LIMIT + 500))

    assert "a" * RAW_TEXT_LIMIT in text
    assert "a" * (RAW_TEXT_LIMIT + 1) not in text
    assert f"{RAW_TEXT_LIMIT + 500} characters, cut at {RAW_TEXT_LIMIT}" in text


def test_a_log_that_cannot_be_written_only_warns(tmp_path, caplog):
    blocker = tmp_path / "logs"
    blocker.write_text("a file where the folder should be", encoding="utf-8")

    log_file = blocker / "x.log"

    write_rejected_reply("CVDA-2026-0001", 1, "onprem", "m", ["p"], "raw", log_file=log_file)

    assert "Could not write the rejected-reply log" in caplog.text


# --- the engine's hook ---


def run(client, charter):
    record = RequestRecord(request_id="CVDA-2026-0001", rulebook_version=1)
    return interpret(client, "Q?", "answer", record, charter, 1, "answer")


def test_one_entry_per_rejected_attempt_with_the_raw_text(seed_rulebook):
    client = StubClient("first bad reply", "second bad reply")

    result = run(client, seed_rulebook.charter)

    text = da_rejected_reply_log.LOG_FILE.read_text(encoding="utf-8")
    assert not result.ok
    assert text.count("=== 20") == 2
    assert "attempt 1" in text and "attempt 2" in text
    assert "first bad reply" in text and "second bad reply" in text
    assert "provider stub" in text and "model stub-model" in text
    assert "request CVDA-2026-0001" in text


def test_a_reply_that_works_on_the_second_try_logs_only_the_first(seed_rulebook):
    client = StubClient("not json", stub_reply())

    result = run(client, seed_rulebook.charter)

    text = da_rejected_reply_log.LOG_FILE.read_text(encoding="utf-8")
    assert result.ok and result.attempts == 2
    assert text.count("=== 20") == 1 and "not json" in text


def test_a_good_reply_writes_nothing(seed_rulebook):
    run(StubClient(stub_reply()), seed_rulebook.charter)

    assert not da_rejected_reply_log.LOG_FILE.exists()


def test_the_conversation_carries_on_when_the_log_cannot_be_written(
    seed_rulebook, tmp_path, monkeypatch
):
    blocker = tmp_path / "blocked"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    monkeypatch.setattr(da_rejected_reply_log, "LOG_FILE", blocker / "rejected.log")

    result = run(StubClient("bad", stub_reply()), seed_rulebook.charter)

    assert result.ok and result.attempts == 2


def test_a_reply_that_cannot_be_encoded_only_warns(tmp_path, caplog):
    # A lone surrogate (from a JSON "\ud800" escape) cannot be written as UTF-8.
    log_file = tmp_path / "rejected.log"

    raw = "bad \ud800 text"

    write_rejected_reply("CVDA-2026-0001", 1, "onprem", "m", ["p"], raw, log_file=log_file)

    assert "Could not write the rejected-reply log (UnicodeEncodeError)" in caplog.text


def test_entry_names_the_step_and_defaults_to_understand(tmp_path):
    log_file = tmp_path / "log.txt"

    text = entry(log_file)
    assert "step understand | attempt 1" in text

    text = entry(log_file, step="discover")
    assert "step discover | attempt 1" in text
