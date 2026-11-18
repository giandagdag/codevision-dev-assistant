"""Nightly refresh (fix 11-3; AH-10, AH-17). Fake clock, fake embedder, no AI, no network."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agents import da_admin_rebuild as rebuild
from agents import da_admin_scheduler as scheduler
from agents.da_admin_index import recent_runs, run_line
from agents.da_code_index import FakeEmbedder
from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file
from layouts.da_admin_index_panels import MERGE_DISABLED_REASON, refresh_tiles

# 02:05 Singapore time on 19 Nov = 18:05 UTC on 18 Nov
AFTER_TWO = datetime(2026, 11, 18, 18, 5, tzinfo=UTC)
BEFORE_TWO = datetime(2026, 11, 18, 17, 55, tzinfo=UTC)
NEXT_NIGHT = datetime(2026, 11, 19, 18, 5, tzinfo=UTC)


def _policy(scope: str, mode: str = "nightly", at: str = "02:00"):
    seed = load_rulebook_file(SEED_RULEBOOK_FILE).policy
    return seed.model_copy(update={
        "index_folder_scope": scope, "index_exclusions": [],
        "index_refresh_mode": mode, "index_nightly_time": at,
    })  # fmt: skip


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "code"
    source.mkdir()
    (source / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return source


def _wire(monkeypatch, policy, tmp_path):
    version = SimpleNamespace(rulebook=SimpleNamespace(policy=policy))
    monkeypatch.setattr(scheduler, "get_active_version", lambda _db: version)
    settings = SimpleNamespace(db_path="x", llm_provider="fake")
    out = tmp_path / "idx"

    def start(policy, user, **kw):  # same call, but a temp folder, the fake embedder, no tagging
        kw.update(directory=out, embedder=FakeEmbedder(), wait=True, settings=None)
        return rebuild.start_rebuild(policy, user, **kw)

    return settings, out, start


def test_is_due_only_for_nightly_after_the_time_and_once_a_day():
    nightly = _policy("")
    assert not scheduler.is_due(nightly, BEFORE_TWO, None)
    assert scheduler.is_due(nightly, AFTER_TWO, None)
    assert not scheduler.is_due(nightly, AFTER_TWO, scheduler.sgt(AFTER_TWO).date())
    assert scheduler.is_due(nightly, NEXT_NIGHT, scheduler.sgt(AFTER_TWO).date())
    assert not scheduler.is_due(_policy("", mode="manual"), AFTER_TWO, None)
    assert not scheduler.is_due(_policy("", mode="merge"), AFTER_TWO, None)


def test_nightly_runs_one_delta_job_with_a_nightly_row(monkeypatch, tmp_path):
    settings, out, start = _wire(monkeypatch, _policy(str(_source(tmp_path))), tmp_path)
    day = scheduler.tick(settings, BEFORE_TWO, None, start)
    assert recent_runs(out) == []  # not yet
    day = scheduler.tick(settings, AFTER_TWO, day, start)
    runs = recent_runs(out)
    assert len(runs) == 1 and runs[0]["trigger"] == "Nightly"
    assert "(Nightly)" in run_line(runs[0])
    scheduler.tick(settings, AFTER_TWO, day, start)  # same night again: nothing new
    assert len(recent_runs(out)) == 1


def test_a_second_server_process_does_not_start_a_second_job(monkeypatch, tmp_path):
    settings, out, start = _wire(monkeypatch, _policy(str(_source(tmp_path))), tmp_path)
    assert rebuild._take_lock(datetime.now(), out)  # the other process holds the lock
    scheduler.tick(settings, AFTER_TWO, None, start)
    assert recent_runs(out) == []


def test_nightly_time_must_be_hh_mm_and_the_tiles_show_merge_disabled():
    with pytest.raises(ValidationError):
        bad = {**_policy("").model_dump(), "index_nightly_time": "25:99"}
        type(_policy("")).model_validate(bad)
    tiles = refresh_tiles("nightly", "03:30")
    assert len(tiles.children) == 3 and tiles.cols == 3  # equal width
    assert tiles.children[0].style == {"height": "100%", "opacity": 0.5}
    assert MERGE_DISABLED_REASON in str(tiles)
    assert "03:30" in str(tiles)
