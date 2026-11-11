"""Phase A fix 3, AS-8: the ops tests must not touch the real ledger or `logs/workers/`.

The file name starts with `zz` so it runs after the other ops tests. The snapshot was taken once
at the start of the pytest session (see conftest).
"""

from tests.ops.conftest import REAL_LOGS, SNAPSHOT, snapshot, status_snapshot


def test_as8_real_ledger_and_worker_folder_are_unchanged():
    assert snapshot(REAL_LOGS) == SNAPSHOT["before"]


def test_fix6_as9_real_status_md_and_its_backup_are_unchanged():
    assert status_snapshot() == SNAPSHOT["status"]


def test_the_snapshot_notices_a_new_ledger_row_and_a_new_reply_file(tmp_path):
    (tmp_path / "workers").mkdir()
    (tmp_path / "usage-ledger.csv").write_text("a\n", encoding="utf-8")
    before = snapshot(tmp_path)
    (tmp_path / "usage-ledger.csv").write_text("a\nb\n", encoding="utf-8")
    assert snapshot(tmp_path) != before
    before = snapshot(tmp_path)
    (tmp_path / "workers" / "20270115-080000-chief.json").write_text("{}", encoding="utf-8")
    assert snapshot(tmp_path) != before
