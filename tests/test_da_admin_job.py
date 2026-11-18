"""Index job status, Stop, one lock, work safety (fix 11-3; AH-7, AH-11). No AI, no network."""

from datetime import datetime, timedelta
from pathlib import Path

from agents import da_admin_job as job
from agents import da_admin_rebuild as rebuild
from agents.da_admin_index import recent_runs
from agents.da_code_index import PIECES_NAME, FakeEmbedder
from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file


def _policy(scope: str):
    seed = load_rulebook_file(SEED_RULEBOOK_FILE).policy
    return seed.model_copy(update={"index_folder_scope": scope, "index_exclusions": []})


def _source(tmp_path: Path, files: int = 3) -> Path:
    source = tmp_path / "code"
    source.mkdir()
    for n in range(files):
        (source / f"m{n}.py").write_text(f"def f{n}():\n    return {n}\n", encoding="utf-8")
    return source


def test_long_job_with_a_heartbeat_stays_locked_even_from_another_process(tmp_path):
    out = tmp_path / "idx"
    # begun before this server, 3 h ago
    started = (rebuild.SERVER_STARTED - timedelta(hours=3)).replace(microsecond=0)
    now = datetime.now()
    assert rebuild._take_lock(started, out)
    job.begin(out, started, "Admin", "full", "Manual")
    job.progress(out, 5, 100, now=now)  # alive just now
    assert rebuild.running_since(now + timedelta(minutes=5), out) == started
    started_again, message = rebuild.start_rebuild(_policy(""), "Admin", directory=out)
    assert (started_again, message) == (False, rebuild.ALREADY_RUNNING)
    # no sign of life for 31 minutes: the job is dead and the lock goes
    assert rebuild.running_since(now + timedelta(minutes=31), out) is None


def test_progress_line_percent_and_time_left_after_20_items(tmp_path):
    out = tmp_path / "idx"
    start = datetime(2026, 11, 18, 9, 0, 0)
    job.begin(out, start, "Admin", "delta", "Manual")
    job.progress(out, 10, 1200, now=start + timedelta(minutes=10))
    early = job.progress_line(job.read_status(out), start + timedelta(minutes=10))
    assert early == "Step 1 of 2: reading the code, 10 of 1,200 pieces (0%)"  # under 20 items
    job.progress(out, 340, 1200, now=start + timedelta(minutes=34))
    status = job.read_status(out)
    line = job.progress_line(status, start + timedelta(minutes=34))
    assert line.startswith("Step 1 of 2: reading the code, 340 of 1,200 pieces (28%)")
    assert line.endswith("About 1 h 26 min left")  # 34 min / 340 pieces * 860 pieces


def test_run_writes_status_row_with_mode_and_stays_readable_after(tmp_path):
    out = tmp_path / "idx"
    source = _source(tmp_path)
    started, _ = rebuild.start_rebuild(
        _policy(str(source)), "Admin", embedder=FakeEmbedder(), directory=out, wait=True,
        mode="delta",
    )
    assert started
    row = recent_runs(out)[0]
    assert row["saved"] and row["mode"] == "full" and row["trigger"] == "Manual"  # nothing to reuse
    assert row["reread"] == 3 and "seconds" in row
    status = job.read_status(out)
    assert status["done"] == 3 and status["total"] == 3 and job.percent(status) == 100
    assert not (out / rebuild.LOCK_NAME).exists()


def test_stop_keeps_the_old_index(tmp_path):
    out = tmp_path / "idx"
    source = _source(tmp_path)
    policy = _policy(str(source))
    rebuild.start_rebuild(policy, "Admin", embedder=FakeEmbedder(), directory=out, wait=True)
    before = (out / PIECES_NAME).read_text(encoding="utf-8")

    class StopsItself(FakeEmbedder):
        def embed(self, text):
            job.request_stop(out)  # the Stop button, clicked while the job runs
            return super().embed(text)

    (source / "m0.py").write_text("def f0():\n    return 'new'\n", encoding="utf-8")
    rebuild.start_rebuild(policy, "Admin", embedder=StopsItself(), directory=out, wait=True)
    row = recent_runs(out)[0]
    assert not row["saved"] and "Stopped" in row["message"]
    assert (out / PIECES_NAME).read_text(encoding="utf-8") == before
    assert not job.stop_requested(out)  # the request is cleared when the job ends


def test_failed_rebuild_keeps_the_error_for_the_page(tmp_path):
    class Boom:
        def embed(self, text):
            raise RuntimeError("Set DA_CODEVISION_SRC")

    out = tmp_path / "idx"
    rebuild.start_rebuild(_policy(str(_source(tmp_path))), "Admin", embedder=Boom(),
                          directory=out, wait=True)
    assert "Set DA_CODEVISION_SRC" in job.read_status(out)["error"]


def test_onprem_refuses_the_made_up_folder(tmp_path):
    out = tmp_path / "idx"
    for scope in ("src/data/da_fake_codevision", "C:/x/src/data/da_fake_codevision/src"):
        started, message = rebuild.start_rebuild(_policy(scope), "Admin", directory=out,
                                                 provider="onprem")
        assert (started, message) == (False, rebuild.MADE_UP_SCOPE_REFUSED)
    assert not (out / rebuild.LOCK_NAME).exists()
    # the same folder is fine at home
    assert rebuild.scope_refusal(_policy("src/data/da_fake_codevision"), "fake") == ""


def test_onprem_empty_scope_means_the_codevision_src_setting(monkeypatch, tmp_path):
    from types import SimpleNamespace

    settings = SimpleNamespace(codevision_src=str(tmp_path / "cv src"), codevision_python="")
    monkeypatch.setattr(rebuild, "load_settings", lambda: settings)
    assert rebuild.source_folder(_policy(""), "onprem") == tmp_path / "cv src"
    assert rebuild.source_folder(_policy(""), "fake") != tmp_path / "cv src"
