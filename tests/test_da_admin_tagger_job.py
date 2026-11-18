"""Phase 11 fix 3, step 4: tagging is step 2 of the index job (AH-8, AH-9). Scripted client only."""

import json
from pathlib import Path

from agents import da_admin_job as job
from agents import da_admin_rebuild as rebuild
from agents import da_admin_tagger_job as tagjob
from agents.da_admin_index import recent_runs
from agents.da_admin_tag_store import read_tags, save_store
from agents.da_admin_tagger import ScriptedTaggerClient, run_tagging, text_hash
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
    return policy, ScriptedTaggerClient({f"m{n}.py": GOOD for n in range(count)}), source


def _job(policy, out, client, settings, mode="full"):
    return rebuild.start_rebuild(
        policy, "admin1", embedder=FakeEmbedder(), directory=out, wait=True, mode=mode,
        settings=settings, tag_client=client,
    )


def test_full_tags_everything_and_the_run_row_says_so(tmp_path, make_settings):
    policy, client, _ = _setup(tmp_path)
    out = tmp_path / "idx"

    started, _ = _job(policy, out, client, make_settings())

    assert started and set(read_tags(out)) == {"m0.py", "m1.py", "m2.py"}
    row = recent_runs(out)[0]
    assert row["tagged"] == 3 and "Tagged 3 programs" in row["message"]
    assert job.read_status(out)["step"] == 2 and not rebuild._lock_path(out).exists()


def test_delta_tags_only_new_or_changed_programs(tmp_path, make_settings):
    policy, client, source = _setup(tmp_path)
    out = tmp_path / "idx"
    _job(policy, out, client, make_settings())
    (source / "m1.py").write_text("x = 99\n", encoding="utf-8")
    seen = []

    class Counting(ScriptedTaggerClient):
        def complete(self, prompt, system=None):
            seen.append(prompt)
            return super().complete(prompt, system)

    _job(policy, out, Counting({"m1.py": GOOD}), make_settings(), mode="delta")

    assert len(seen) == 1 and "m1.py" in seen[0]
    assert recent_runs(out)[0]["tagged"] == 1


def test_over_ten_percent_failing_keeps_the_index_and_says_tags_not_saved(tmp_path, make_settings):
    policy, _, _ = _setup(tmp_path)
    out = tmp_path / "idx"

    class Broken:
        def complete(self, prompt, system=None):
            raise RuntimeError("down")

    _job(policy, out, Broken(), make_settings())

    row = recent_runs(out)[0]
    assert row["saved"] and tagjob.TAGS_NOT_SAVED in row["message"]  # the index was kept
    assert (out / "da_code_index.json").exists() and read_tags(out) == {}


def test_stop_during_tagging_keeps_the_index_and_drops_the_new_tags(tmp_path, make_settings):
    policy, _, _ = _setup(tmp_path)
    out = tmp_path / "idx"

    class StopsAfterFirst(ScriptedTaggerClient):
        def complete(self, prompt, system=None):
            job.request_stop(out)
            return super().complete(prompt, system)

    client = StopsAfterFirst({f"m{n}.py": GOOD for n in range(3)})
    _job(policy, out, client, make_settings())

    row = recent_runs(out)[0]
    assert row["saved"] and "Stopped" in row["message"] and read_tags(out) == {}


def test_a_changed_file_keeps_the_approved_state_and_capability(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    (src / "m0.py").write_text("x = 2\n")
    old = {"file_hash": text_hash("x = 1\n"), "summary": "Old.", "proposed_capability": "Reports",
           "confidence": "high", "reason": "r", "state": "approved"}
    save_store({"modules": {"m0.py": old}, "runs": []}, out)
    reply = {**GOOD, "summary": "New words."}

    run_tagging(["m0.py"], src, [], ScriptedTaggerClient({"m0.py": json.dumps(reply)}), "a",
                directory=out)

    kept = read_tags(out)["m0.py"]
    assert kept["state"] == "approved" and kept["proposed_capability"] == "Reports"
    assert kept["summary"] == "New words." and kept["file_hash"] == text_hash("x = 2\n")


def test_the_tagger_role_and_its_model_are_used_at_work(monkeypatch, make_settings):
    seen = {}
    monkeypatch.setattr(
        tagjob, "get_llm_client", lambda role, settings, model: seen.update(role=role, model=model)
    )
    policy = load_rulebook_file(SEED_RULEBOOK_FILE).policy.model_copy(
        update={"tagger_model": "tag-model-x"}
    )

    tagjob.pick_client(make_settings(llm_provider="onprem"), policy)

    assert seen == {"role": "tagger", "model": "tag-model-x"}
    assert isinstance(tagjob.pick_client(make_settings(), policy), ScriptedTaggerClient)


def test_the_scan_buttons_are_gone_from_the_catalog_tab():
    from pathlib import Path as P

    text = (P(__file__).parents[1] / "src/layouts/da_admin_catalog_tab.py").read_text("utf-8")
    assert "Scan all programs" not in text and "scan_controls" not in text
