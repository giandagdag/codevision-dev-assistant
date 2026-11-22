import pytest

from agents.da_safety_gate import KIND_BOTH, KIND_DESTRUCTIVE, KIND_INTENT, KIND_NONE, scan


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Add a column to the customer report", KIND_NONE),
        ("I need a program to delete all database tables", KIND_DESTRUCTIVE),
        ("Wipe the staging files", KIND_DESTRUCTIVE),
        ("Please disable logging for the batch", KIND_DESTRUCTIVE),
        ("Truncate the whole schema", KIND_DESTRUCTIVE),
        ("Delete the 2 tables TMP_LOAD_A and TMP_LOAD_B after month end", KIND_NONE),
        ("A report to get back at my manager", KIND_INTENT),
        ("This is revenge for last week", KIND_INTENT),
        ("My boss is stupid, so build me a report", KIND_INTENT),
        ("Delete all database tables because I hate my boss", KIND_BOTH),
        ("My manager asked for a report on small loans", KIND_NONE),
        ("Whatever the report shows is fine", KIND_NONE),
    ],
)
def test_scan_kind(text, kind):
    assert scan(text).kind == kind


def test_scan_returns_the_matched_words():
    result = scan("delete all tables, I hate my boss")
    assert {"delete", "all", "hate", "boss"} <= set(result.words)


def test_scan_is_the_same_every_time():
    assert scan("sabotage the job") == scan("sabotage the job")
