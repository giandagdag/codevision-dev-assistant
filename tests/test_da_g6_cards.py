"""Fix G6 S4/S5: the job, the cards and their decisions (G6-1, 4, 5). Made-up only."""

import json
from types import SimpleNamespace

from agents import da_admin_job as job
from agents.da_capability_suggest_job import (
    ScriptedGroupClient,
    should_offer,
    start_suggest,
)
from agents.da_code_graph import build_graph, save_graph
from agents.da_group_cards import (
    create_card,
    read_cards,
    reject_card,
    remove_program,
    save_suggestions,
)
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions

ADMIN = "admin-0001"


def _star(folder: str, leaves: int) -> dict[str, str]:
    names = [f"l{i}" for i in range(leaves)]
    files = {f"{folder}/hub.py": "".join(f"import {folder}.{n}\n" for n in names)}
    return files | {f"{folder}/{n}.py": f"import {folder}.hub\n" for n in names}


def _save(tmp_path, folders: dict[str, int]) -> None:
    files: dict[str, str] = {}
    for folder, leaves in folders.items():
        files |= _star(folder, leaves)
    for name, text in files.items():
        (tmp_path / "src" / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / name).write_text(text, encoding="utf-8")
    save_graph(build_graph(tmp_path / "src", list(files)).graph, tmp_path)


def _policy(db_path):
    return get_active_version(db_path).rulebook.policy


def test_g6_1_the_job_saves_cards_and_creates_nothing(
    db_path, published_rulebook, make_settings, tmp_path
):
    _save(tmp_path, {"alpha": 3, "beta": 3, "gamma_x": 3})

    started, _ = start_suggest(
        _policy(db_path), make_settings(), ADMIN, directory=tmp_path, wait=True
    )

    assert started
    assert sorted(c.name for c in read_cards(tmp_path)) == ["Alpha", "Beta", "Gamma X"]
    assert len(list_versions(db_path)) == 1  # nothing was created
    assert "3 capability suggestions" in job.read_status(tmp_path)["end_line"]


def test_g6_5_the_bar_names_the_step_and_the_lock_is_freed(tmp_path):
    job.begin(tmp_path, __import__("datetime").datetime.now(), ADMIN, "suggest", "Manual")
    job.set_step_name(tmp_path, "Naming groups", 2)

    status = job.read_status(tmp_path)

    assert job.step_title(status) == "Naming groups"
    assert job.progress_line(status) == "Step 2 of 3: naming groups"


def test_the_fake_client_answers_both_prompts():
    client = ScriptedGroupClient()

    assert json.loads(client.complete("Suggested areas:\n- x").text) == {"merges": []}
    assert SimpleNamespace(**json.loads(client.complete("- alpha/a.py: s").text)).name == "Alpha"


def test_button_shows_with_few_capabilities_or_many_unassigned():
    assert should_offer(4, 0, 100) and should_offer(8, 31, 100)
    assert not should_offer(8, 30, 100) and not should_offer(5, 0, 0)


def _group(name="Docs", programs=("a/x.py", "a/y.py", "a/z.py")):
    from agents.da_capability_suggest import NamedGroup

    return NamedGroup(name, "Writes docs.", programs, "high", ("a",), 4, 1)


def test_g6_4_create_and_assign_after_removing_one_program(
    db_path, published_rulebook, make_settings, tmp_path
):
    save_suggestions([_group()], tmp_path)
    remove_program("Docs", "a/z.py", tmp_path)

    [card] = read_cards(tmp_path)
    assert card.programs == ("a/x.py", "a/y.py") and card.counts == "2 programs, 4 links inside"

    result = create_card(make_settings(), "Docs", "Writes docs.", "Ana Cruz", "", ADMIN, "Docs",
                         1, tmp_path)

    assert result.kind == "resolved" and len(list_versions(db_path)) == 2
    active = get_active_version(db_path)
    assert active.change_note == "Suggested from code links: new capability Docs with 2 programs"
    new = next(c for c in active.rulebook.policy.capabilities if c.name == "Docs")
    assert new.path_patterns == ["a/x.py", "a/y.py"]  # the removed program stays unassigned
    assert read_cards(tmp_path) == []


def test_a_refused_create_keeps_the_card(db_path, published_rulebook, make_settings, tmp_path):
    save_suggestions([_group()], tmp_path)

    result = create_card(make_settings(), "Docs", "d", " ", "", ADMIN, "Docs", 1, tmp_path)

    assert result.kind == "refused" and len(read_cards(tmp_path)) == 1


def test_reject_survives_a_new_run_with_the_same_group(tmp_path):
    save_suggestions([_group()], tmp_path)
    reject_card("Docs", tmp_path)

    assert read_cards(tmp_path) == []
    assert save_suggestions([_group()], tmp_path) == 0  # same name and programs: stays rejected
    assert save_suggestions([_group(programs=("a/x.py", "a/q.py"))], tmp_path) == 1
