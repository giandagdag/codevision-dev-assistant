"""Rebuild index from Admin (fix 11-1, AF-7, AF-8). Fake embedders only, no AI, no network."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from agents import da_admin_rebuild as rebuild
from agents.da_admin_index import RUNS_NAME, read_health, recent_runs, run_line
from agents.da_code_index import PIECES_NAME, FakeEmbedder, WorkEmbedder
from da_build_code_index import build_index
from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file
from pydantic_classes.da_rulebook_models import IndexExclusion


def _source(tmp_path: Path, files: int = 4) -> Path:
    source = tmp_path / "src_folder"
    (source / "build").mkdir(parents=True)
    for n in range(files):
        (source / f"mod{n}.py").write_text(f"def f{n}():\n    return {n}\n", encoding="utf-8")
    (source / "build" / "gen.py").write_text("def made():\n    return 1\n", encoding="utf-8")
    return source


def _policy(source: Path | None, *patterns: str):
    seed = load_rulebook_file(SEED_RULEBOOK_FILE).policy
    excluded = [IndexExclusion(pattern=p, reason="r", kind="Build") for p in patterns]
    return seed.model_copy(
        update={"index_folder_scope": str(source or ""), "index_exclusions": excluded}
    )


def _run(policy, embedder, out):
    return rebuild.start_rebuild(policy, "Admin", embedder=embedder, directory=out, wait=True)


class _FailFirst:
    """Fails for the first N pieces, then works."""

    def __init__(self, fails: int) -> None:
        self.left = fails
        self.inner = FakeEmbedder()

    def embed(self, text: str):
        if self.left > 0:
            self.left -= 1
            return None
        return self.inner.embed(text)


def test_extra_exclusions_are_left_out(tmp_path):
    source = _source(tmp_path)
    out = tmp_path / "idx"
    build_index(source, out, FakeEmbedder(), say=lambda _t: None, extra_exclusions=["*/build/*"])
    paths = {p["path"] for p in json.loads((out / PIECES_NAME).read_text())["pieces"]}
    assert "build/gen.py" not in paths and "mod0.py" in paths


def test_no_extra_exclusions_keeps_everything(tmp_path):
    out = tmp_path / "idx"
    build_index(_source(tmp_path), out, FakeEmbedder(), say=lambda _t: None)
    assert read_health(out).modules == 5


def test_rebuild_done_row_and_excluded_file_gone(tmp_path):
    out = tmp_path / "idx"
    policy = _policy(_source(tmp_path), "*/build/*")
    started, _ = _run(policy, FakeEmbedder(), out)
    assert started
    paths = {p["path"] for p in json.loads((out / PIECES_NAME).read_text())["pieces"]}
    assert "build/gen.py" not in paths
    row = recent_runs(out)[0]
    assert row["saved"] and "✅ Done" in run_line(row) and "4 pieces" in run_line(row)
    assert not (out / rebuild.LOCK_NAME).exists()


def test_one_piece_skipped_is_named(tmp_path):
    out = tmp_path / "idx"
    source = tmp_path / "s"
    source.mkdir()
    for n in range(20):
        (source / f"m{n}.py").write_text(f"def f{n}():\n    return 1\n", encoding="utf-8")
    _run(_policy(source), _FailFirst(1), out)
    row = recent_runs(out)[0]
    assert row["saved"] and "⚠️ 1 piece skipped" in run_line(row)
    assert row["skipped"] == ["m0.py f0"]


def test_three_of_twenty_not_saved_and_old_index_stays(tmp_path):
    out = tmp_path / "idx"
    source = tmp_path / "s"
    source.mkdir()
    for n in range(20):
        (source / f"m{n}.py").write_text(f"def f{n}():\n    return 1\n", encoding="utf-8")
    _run(_policy(source), FakeEmbedder(), out)
    before = (out / PIECES_NAME).read_text()
    _run(_policy(source), _FailFirst(3), out)
    row = recent_runs(out)[0]
    assert not row["saved"] and "❌ Not saved" in run_line(row)
    assert (out / PIECES_NAME).read_text() == before


def test_second_click_refused_while_running(tmp_path):
    out = tmp_path / "idx"
    out.mkdir()
    (out / rebuild.LOCK_NAME).write_text(json.dumps({"started": datetime.now().isoformat()}))
    started, message = rebuild.start_rebuild(_policy(_source(tmp_path)), "Admin", directory=out)
    assert not started and message == rebuild.ALREADY_RUNNING
    assert not (out / RUNS_NAME).exists()


def test_old_or_pre_start_lock_is_cleared(tmp_path):
    out = tmp_path / "idx"
    out.mkdir()
    old = datetime.now() - timedelta(hours=3)
    (out / rebuild.LOCK_NAME).write_text(json.dumps({"started": old.isoformat()}))
    assert rebuild.running_since(directory=out) is None
    assert not (out / rebuild.LOCK_NAME).exists()
    # A lock written before this server started is also cleared.
    early = rebuild.SERVER_STARTED - timedelta(minutes=1)
    (out / rebuild.LOCK_NAME).write_text(json.dumps({"started": early.isoformat()}))
    assert rebuild.running_since(early + timedelta(minutes=2), out) is None


def test_failed_job_frees_the_lock_and_logs(tmp_path):
    class Boom:
        def embed(self, text):
            raise RuntimeError("only works at work")

    out = tmp_path / "idx"
    _run(_policy(_source(tmp_path)), Boom(), out)
    assert not recent_runs(out)[0]["saved"]
    assert not (out / rebuild.LOCK_NAME).exists()


def test_embedder_follows_provider():
    assert isinstance(rebuild.pick_embedder("onprem"), WorkEmbedder)
    assert isinstance(rebuild.pick_embedder("fake"), FakeEmbedder)


def test_rebuild_click_passes_the_settings_provider_not_the_environment(monkeypatch):
    """Review round 1: .env never fills os.environ, so the provider must come from the settings."""
    from callbacks.screen_callbacks import da_admin_page_callbacks as admin_cb

    monkeypatch.delenv("DA_LLM_PROVIDER", raising=False)
    seen = {}

    def fake_start(policy, who, provider=""):
        seen["provider"] = provider
        return True, "ok"

    settings = type("S", (), {"developer_id": "a1", "llm_provider": "onprem", "db_path": "x"})()
    monkeypatch.setattr(admin_cb, "is_admin", lambda *_: True)
    monkeypatch.setattr(admin_cb, "get_active_version", lambda _db: type(
        "V", (), {"rulebook": type("R", (), {"policy": None})()})())
    monkeypatch.setattr(admin_cb, "start_rebuild", fake_start)
    monkeypatch.setattr(admin_cb, "current_rebuild_status", lambda: "")
    admin_cb.rebuild_action(settings, admin_cb.REBUILD_CONFIRM)
    assert seen["provider"] == "onprem"


def test_source_folder_order(monkeypatch, tmp_path):
    monkeypatch.delenv("DA_CODE_INDEX_SOURCE", raising=False)
    assert rebuild.source_folder(_policy(None)) == rebuild.SRC_FOLDER
    monkeypatch.setenv("DA_CODE_INDEX_SOURCE", str(tmp_path))
    assert rebuild.source_folder(_policy(None)) == tmp_path
    scoped = rebuild.source_folder(_policy(Path("src/data/da_fake_codevision")))
    assert scoped == rebuild.PROJECT_ROOT / "src/data/da_fake_codevision"
