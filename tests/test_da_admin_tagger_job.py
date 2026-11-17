"""Phase 11 fix 2, step 4: the AI scan job (AG-8). Made-up files, scripted client, no real AI."""

from datetime import datetime
from pathlib import Path

from agents import da_admin_rebuild as rebuild
from agents import da_admin_tagger_job as job
from agents.da_admin_tag_store import read_tags
from agents.da_admin_tagger import ScriptedTaggerClient
from agents.da_code_index import FakeEmbedder
from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file

GOOD = {"summary": "Does a thing.", "capability": "none", "confidence": "low", "reason": "ok"}


def _setup(tmp_path: Path, count: int = 3):
    source = tmp_path / "src_folder"
    source.mkdir()
    for n in range(count):
        (source / f"m{n}.py").write_text(f"x = {n}\n", encoding="utf-8")
    policy = load_rulebook_file(SEED_RULEBOOK_FILE).policy.model_copy(
        update={"index_folder_scope": str(source), "index_exclusions": []}
    )
    client = ScriptedTaggerClient({f"m{n}.py": GOOD for n in range(count)})
    return policy, client


def test_scan_saves_tags_frees_the_lock_and_counts_progress(tmp_path, make_settings):
    policy, client = _setup(tmp_path)
    out = tmp_path / "idx"

    started, _ = job.start_scan(
        policy, make_settings(), "admin1", directory=out, client=client, wait=True
    )

    assert started and set(read_tags(out)) == {"m0.py", "m1.py", "m2.py"}
    assert job.scan_running(out) is None
    assert job.progress_text() == "Scanning… 3 of 3"
    assert job.status_line(out) == "Done: 3 scanned, 3 proposals."


def test_scan_refused_while_a_rebuild_runs_and_the_other_way_round(tmp_path, make_settings):
    policy, client = _setup(tmp_path)
    out = tmp_path / "idx"
    now = datetime.now()

    rebuild._take_lock(now, out)  # a rebuild is running
    started, message = job.start_scan(policy, make_settings(), "a", directory=out, client=client)
    assert (started, message) == (False, rebuild.ONE_JOB_AT_A_TIME)
    rebuild._lock_path(out).unlink()

    rebuild._take_lock(now, out, rebuild.TAGGER_LOCK_NAME)  # a scan is running
    started, message = rebuild.start_rebuild(
        policy, "a", embedder=FakeEmbedder(), directory=out, wait=True
    )
    assert (started, message) == (False, rebuild.ONE_JOB_AT_A_TIME)
    assert not rebuild._lock_path(out).exists()


def test_a_second_scan_is_refused(tmp_path, make_settings):
    policy, client = _setup(tmp_path)
    out = tmp_path / "idx"
    rebuild._take_lock(datetime.now(), out, rebuild.TAGGER_LOCK_NAME)

    started, message = job.start_scan(policy, make_settings(), "a", directory=out, client=client)

    assert (started, message) == (False, rebuild.ONE_JOB_AT_A_TIME)


def test_cap_leaves_the_rest_for_the_next_scan(tmp_path, make_settings):
    policy, client = _setup(tmp_path, count=3)
    out = tmp_path / "idx"

    job.start_scan(
        policy, make_settings(tagger_max_modules=2), "a", directory=out, client=client, wait=True
    )

    assert len(read_tags(out)) == 2
    assert job.status_line(out) == "Done: 2 scanned, 2 proposals. 1 more wait for the next scan."


def test_a_failing_job_still_frees_the_lock(tmp_path, make_settings):
    policy, _ = _setup(tmp_path)
    out = tmp_path / "idx"

    class Broken:
        def complete(self, prompt, system=None):
            raise RuntimeError("down")

    job.start_scan(policy, make_settings(), "a", directory=out, client=Broken(), wait=True)

    assert job.scan_running(out) is None
    assert "not saved" in job.status_line(out).lower()  # every module failed: over 10%


def test_non_admin_cannot_start_a_scan(make_settings):
    import pytest
    from dash.exceptions import PreventUpdate

    from callbacks.screen_callbacks.da_admin_scan_callbacks import scan_action
    from layouts.da_admin_scan_controls import SCAN_CONFIRM

    with pytest.raises(PreventUpdate):
        scan_action(make_settings(developer_id="nobody-9"), SCAN_CONFIRM, "all")


def test_the_catalog_tab_shows_the_scan_buttons():
    from layouts.da_admin_scan_controls import scan_controls

    shown = str(scan_controls(False, "", True))
    assert "Scan all programs" in shown and "Tag new or changed" in shown


def test_the_tagger_role_and_its_model_are_used_at_work(monkeypatch, make_settings):
    seen = {}
    monkeypatch.setattr(
        job, "get_llm_client", lambda role, settings, model: seen.update(role=role, model=model)
    )
    policy = load_rulebook_file(SEED_RULEBOOK_FILE).policy.model_copy(
        update={"tagger_model": "tag-model-x"}
    )

    job.pick_client(make_settings(llm_provider="onprem"), policy)

    assert seen == {"role": "tagger", "model": "tag-model-x"}
    assert isinstance(job.pick_client(make_settings(), policy), ScriptedTaggerClient)
