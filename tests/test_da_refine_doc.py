from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "docs" / "refine-work-test.md"


def test_work_test_doc_has_no_known_gap_note():
    # The Refine callbacks are wired (step 16), so the "not wired yet" note must be gone.
    assert "Known gap" not in DOC.read_text(encoding="utf-8")
