"""The browser script in a real browser (Phase 5 step 10).

Rows 5-15 (same fingerprint as Python), 5-16 (line endings kept on disk), 5-11 and 5-12/5-13
(browser half of the path rules and the edit guard), 6-39 and 6-40 (only planned files are read),
5-23 and 6-40 (the ZIP holds code files only), 6-36 (the writer makes no folder). Skipped, not
failed, when Playwright is missing.
"""

import zipfile

import pytest

from agents.da_workspace_checks import fingerprint
from tests.da_browser import HAS_DIR_JS, READ_JS, SEED_JS

TESTS = "tests/cvda_2026_0001"  # a folder Phase 5 used; Phase 6 never reads or writes it
CTX = {
    "planned_paths": ["src/agents/excel_processor.py", "src/agents/upload_validator.py"],
    "markers": ["src/web", "src/callbacks"],
    "max_file_kb": 512,
}
TREE = {
    "src/web/da_page.py": "# web\n",
    "src/callbacks/da_calls.py": "# callbacks\n",
    "src/agents/upload_validator.py": "def validate(path):\n    return True\n",
    "src/agents/secret_notes.py": "never read\n",
    "README.md": "never read either\n",
}


def pick(page, key="choose"):
    return page.evaluate("([key, ctx]) => window.daWorkspace.handle(key, ctx)", [key, CTX])


def job(page, items):
    return {
        "request_id": "CVDA-2026-0001",
        "folder_name": "x",
        "files": [{"path": p, "text": t, "expected": e} for p, t, e in items],
    }


def run(page, the_job):
    return page.evaluate("(j) => window.daWorkspace.write(j)", the_job)


# --- 5-15: the same code in Python and in the browser ---

TEXTS = [
    "",
    "# hi\n",
    "a = 1\r\nb = 2\r\n",
    "\ufeffwith a byte order mark\n",
    "naïve café – ünïcode ✓\n",
    "mixed\r\nendings\nand\rold mac\n",
]


@pytest.mark.parametrize("text", TEXTS)
def test_5_15_the_browser_fingerprint_equals_the_python_one(make_page, text):
    page = make_page()

    in_browser = page.evaluate("(t) => window.daWorkspace.fingerprint(t)", text)

    assert in_browser == fingerprint(text)


# --- the picker stand-in and the facts ---


def test_the_stand_in_picker_gives_facts_and_remembers_the_folder(make_page):
    page = make_page()
    page.evaluate(SEED_JS, TREE)

    result = pick(page)

    assert result["kind"] == "facts"
    facts = result["facts"]
    assert facts["markers"] == {"src/web": True, "src/callbacks": True}
    assert facts["has_git"] is False and facts["looks_like_src"] is False
    by_path = {f["path"]: f for f in facts["files"]}
    assert by_path["src/agents/excel_processor.py"]["exists"] is False
    assert by_path["src/agents/excel_processor.py"]["parent_exists"] is True
    validator = by_path["src/agents/upload_validator.py"]
    assert validator["text"] == TREE["src/agents/upload_validator.py"]
    assert validator["fingerprint"] == fingerprint(validator["text"])
    chip = page.evaluate("() => window.daWorkspace.chip()")
    assert chip["permission"] == "granted"


def test_6_39_files_outside_the_plan_and_a_tests_folder_are_never_opened(make_page):
    """Phase 6 (C3, C4): only planned files are read; a tests folder is not looked at."""
    page = make_page()
    extra = {f"{TESTS}/__init__.py": "# x\n", f"{TESTS}/test_mine.py": "pass\n"}
    page.evaluate(SEED_JS, {**TREE, **extra})

    result = pick(page)

    opened = set(page.evaluate("() => window.__opened"))
    assert opened == {"upload_validator.py"}  # the one planned file that exists
    assert "secret_notes.py" not in opened and "README.md" not in opened
    assert "test_mine.py" not in opened
    assert "tests_files" not in result["facts"] and "tests_exists" not in result["facts"]


def test_the_git_folder_is_noticed_but_never_opened(make_page):
    page = make_page()
    page.evaluate(SEED_JS, {**TREE, ".git/HEAD": "ref: refs/heads/main\n"})

    result = pick(page)

    assert result["facts"]["has_git"] is True
    assert "HEAD" not in page.evaluate("() => window.__opened")


def test_picking_the_src_folder_itself_is_noticed(make_page):
    page = make_page()
    page.evaluate(SEED_JS, {"web/da_page.py": "x\n", "callbacks/da_calls.py": "y\n"})

    assert pick(page)["facts"]["looks_like_src"] is True


def test_a_file_over_the_limit_is_never_read_and_a_non_utf8_file_is_flagged(make_page):
    page = make_page()
    page.evaluate(SEED_JS, TREE)
    page.evaluate("""async () => {
      const root = await navigator.storage.getDirectory();
      const dir = await (await root.getDirectoryHandle('src')).getDirectoryHandle('agents');
      const handle = await dir.getFileHandle('upload_validator.py', {create: true});
      const w = await handle.createWritable();
      await w.write(new Uint8Array([0xff, 0xfe, 0xfa])); await w.close();
    }""")
    small = {**CTX, "max_file_kb": 1}

    bad = page.evaluate("([ctx]) => window.daWorkspace.handle('choose', ctx)", [CTX])
    page.evaluate(SEED_JS, {"src/agents/upload_validator.py": "x" * 3000})
    big = page.evaluate("([ctx]) => window.daWorkspace.handle('rescan', ctx)", [small])

    def validator(result):
        files = result["facts"]["files"]
        return next(f for f in files if f["path"].endswith("upload_validator.py"))

    assert validator(bad)["not_utf8"] is True and "text" not in validator(bad)
    assert validator(big)["too_big"] is True and "text" not in validator(big)


def test_a_cancelled_picker_and_a_missing_picker_are_reported(make_page):
    page = make_page()
    page.evaluate("""() => { window.showDirectoryPicker = async () => {
        throw new DOMException('closed', 'AbortError'); }; }""")
    assert pick(page) == {"kind": "cancelled"}

    old = make_page(picker=False)
    assert pick(old) == {"kind": "fallback", "reason": "unsupported"}


# --- 5-16, 5-11, 5-12, 5-13: the write job ---


def test_the_job_writes_a_new_code_file_in_an_existing_folder_and_reads_it_back(make_page):
    page = make_page()
    page.evaluate(SEED_JS, TREE)
    pick(page)
    path, text = "src/agents/excel_processor.py", "def read_sheets(workbook):\n    return {}\n"

    report = run(page, job(page, [(path, text, "absent")]))

    assert report["stopped"] is None
    assert report["written"] == [{"path": path, "text": text, "fingerprint": fingerprint(text)}]
    assert page.evaluate(READ_JS, path) == text


def test_6_36_a_job_whose_parent_folder_is_missing_is_refused_and_no_folder_is_made(make_page):
    page = make_page()
    page.evaluate(SEED_JS, TREE)
    pick(page)

    report = run(page, job(page, [(f"{TESTS}/__init__.py", "# x\n", "absent")]))
    new_dir = run(page, job(page, [("src/brand_new/x.py", "x\n", "absent")]))

    assert report["written"] == [] and new_dir["written"] == []
    assert "does not exist, and the app does not create it" in report["stopped"]["reason"]
    assert "does not exist, and the app does not create it" in new_dir["stopped"]["reason"]
    assert page.evaluate(READ_JS, f"{TESTS}/__init__.py") is None
    assert page.evaluate(READ_JS, "src/brand_new/x.py") is None
    assert page.evaluate(HAS_DIR_JS, "tests") is False  # not even the first folder was created
    assert page.evaluate(HAS_DIR_JS, "src/brand_new") is False


def test_5_16_a_crlf_file_keeps_crlf_on_disk(make_page):
    page = make_page()
    original = "x = 1\r\ny = 2\r\n"
    page.evaluate(SEED_JS, {**TREE, "src/agents/upload_validator.py": original})
    pick(page)
    changed = "x = 1\r\ny = 3\r\n"  # the server already sends the file's own line endings

    item = ("src/agents/upload_validator.py", changed, fingerprint(original))
    report = run(page, job(page, [item]))

    assert report["stopped"] is None
    assert page.evaluate(READ_JS, "src/agents/upload_validator.py") == changed
    assert "\r\n" in page.evaluate(READ_JS, "src/agents/upload_validator.py")


def test_5_11_a_path_with_dots_is_refused_and_nothing_is_created(make_page):
    page = make_page()
    page.evaluate(SEED_JS, TREE)
    pick(page)

    for bad in ("../outside.py", "src/../x.py", "./x.py", "src//x.py", "/abs.py", "C:/x.py"):
        report = run(page, job(page, [(bad, "x\n", "absent")]))
        assert report["written"] == [] and "not allowed" in report["stopped"]["reason"]

    assert page.evaluate(READ_JS, "outside.py") is None


def test_the_app_never_creates_a_folder_outside_the_tests_folder(make_page):
    page = make_page()
    page.evaluate(SEED_JS, TREE)
    pick(page)

    report = run(page, job(page, [("src/newfolder/x.py", "x\n", "absent")]))

    assert "does not exist" in report["stopped"]["reason"]
    assert page.evaluate(HAS_DIR_JS, "src/newfolder") is False


def test_5_12_a_changed_file_stops_the_job_and_earlier_files_stay_written(make_page):
    page = make_page()
    page.evaluate(SEED_JS, {**TREE, "src/agents/upload_validator.py": "developer edit\n"})
    pick(page)
    items = [
        ("src/agents/a_first.py", "# a\n", "absent"),
        ("src/agents/upload_validator.py", "generated\n", fingerprint("original\n")),
        ("src/agents/c_last.py", "# c\n", "absent"),
    ]

    report = run(page, job(page, items))

    assert [w["path"] for w in report["written"]] == ["src/agents/a_first.py"]
    assert report["stopped"]["path"] == "src/agents/upload_validator.py"
    assert "Re-scan first" in report["stopped"]["reason"]
    assert page.evaluate(READ_JS, "src/agents/upload_validator.py") == "developer edit\n"
    assert page.evaluate(READ_JS, "src/agents/c_last.py") is None
    assert page.evaluate(READ_JS, "src/agents/a_first.py") == "# a\n"


def test_5_13_a_new_file_that_already_exists_is_stopped(make_page):
    page = make_page()
    page.evaluate(SEED_JS, {**TREE, "src/agents/excel_processor.py": "somebody was here\n"})
    pick(page)

    report = run(page, job(page, [("src/agents/excel_processor.py", "# mine\n", "absent")]))

    assert "already exists" in report["stopped"]["reason"]
    assert page.evaluate(READ_JS, "src/agents/excel_processor.py") == "somebody was here\n"


# --- 5-23 and 5-24: the fallback ---


def test_5_23_and_6_40_download_zip_holds_code_files_and_the_readme_only(make_page, tmp_path):
    page = make_page()
    code = "src/agents/excel_processor.py"
    pack = {
        "files": [{"path": code, "text": "x = 1\n"}],
        "readme_name": "READ_ME_FIRST.txt",
        "readme": "Unzip this file into your CodeVision folder.\r\n",
    }

    with page.expect_download() as info:
        page.evaluate("(p) => window.daWorkspace.download(p)", pack)
    target = tmp_path / "pack.zip"
    info.value.save_as(target)

    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None  # every CRC is right
        assert sorted(archive.namelist()) == sorted([code, "READ_ME_FIRST.txt"])
        assert not any(name.startswith("tests/") for name in archive.namelist())
        assert archive.read(code).decode() == "x = 1\n"
        assert b"Unzip this file" in archive.read("READ_ME_FIRST.txt")


def test_6_40_upload_sends_only_planned_files(make_page, tmp_path):
    folder = tmp_path / "codevision"
    for path, text in {**TREE, f"{TESTS}/test_mine.py": "pass\n"}.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    page = make_page(picker=False)

    # Start the upload without waiting for it: it finishes only after the chooser is answered.
    with page.expect_file_chooser() as chooser:
        page.evaluate(
            "(ctx) => { window.__upload = window.daWorkspace.handle('upload', ctx); }", CTX
        )
    chooser.value.set_files(folder)
    result = page.evaluate("() => window.__upload")

    facts = result["facts"]
    assert result["kind"] == "upload_facts" and facts["folder_name"] == "codevision"
    assert facts["markers"] == {"src/web": True, "src/callbacks": True}
    opened = set(page.evaluate("() => window.__opened"))
    assert opened == {"codevision/src/agents/upload_validator.py"}  # the tests folder is not read
    assert "tests_files" not in facts and "tests_exists" not in facts


def test_reconnect_re_allows_the_remembered_folder_and_with_none_opens_the_picker(make_page):
    page = make_page()
    page.evaluate(SEED_JS, TREE)
    assert pick(page, "reconnect")["kind"] == "facts"  # nothing remembered yet: the picker

    again = pick(page, "reconnect")  # now a folder is remembered

    assert again == {"kind": "reconnected"}
    report = run(page, job(page, [("src/agents/excel_processor.py", "# x\n", "absent")]))
    assert report["stopped"] is None  # the folder is connected again


def test_a_non_utf8_file_stops_the_edit_guard_instead_of_being_guessed(make_page):
    page = make_page()
    page.evaluate(SEED_JS, TREE)
    pick(page)
    page.evaluate("""async () => {
      const root = await navigator.storage.getDirectory();
      const handle = await root.getFileHandle('bad.py', {create: true});
      const w = await handle.createWritable();
      await w.write(new Uint8Array([0xff, 0xfe, 0xfa])); await w.close();
    }""")

    report = run(page, job(page, [("bad.py", "x\n", fingerprint("x\n"))]))

    assert "not a UTF-8" in report["stopped"]["reason"]


# --- 6-32 (P26): same name, different folder ---

TWO_FOLDERS_JS = """
async () => {
  const root = await navigator.storage.getDirectory();
  const first = await root.getDirectoryHandle('codevision', { create: true });
  const elsewhere = await root.getDirectoryHandle('elsewhere', { create: true });
  const second = await elsewhere.getDirectoryHandle('codevision', { create: true });
  window.__next = first;
  window.showDirectoryPicker = async () => window.__next;
  window.__first = first;
  window.__second = second;
}
"""


def test_6_32_a_different_folder_with_the_same_name_is_not_linked_but_the_same_one_still_passes(
    make_page,
):
    page = make_page()
    page.evaluate(TWO_FOLDERS_JS)
    linked_ctx = {**CTX, "folder_name": "codevision", "step": "ws_ready"}

    first = page.evaluate("([k, c]) => window.daWorkspace.handle(k, c)", ["choose", CTX])
    again = page.evaluate("([k, c]) => window.daWorkspace.handle(k, c)", ["choose", linked_ctx])
    page.evaluate("() => { window.__next = window.__second; }")
    other = page.evaluate("([k, c]) => window.daWorkspace.handle(k, c)", ["choose", linked_ctx])
    linked_on_purpose = page.evaluate(
        "([k, c]) => window.daWorkspace.handle(k, c)", ["change_folder", linked_ctx]
    )

    assert first["kind"] == "facts"  # nothing was linked yet: no comparison needed
    assert again["kind"] == "facts"  # the same folder passes
    assert other == {"kind": "different_folder", "name": "codevision"}
    assert linked_on_purpose["kind"] == "facts"  # Change links it on purpose


def test_6_32_a_second_folder_with_another_name_is_not_stopped(make_page):
    page = make_page()
    page.evaluate(TWO_FOLDERS_JS)
    page.evaluate("() => { window.__next = window.__second; }")
    ctx = {**CTX, "folder_name": "some_other_name", "step": "ws_ready"}

    result = page.evaluate("([k, c]) => window.daWorkspace.handle(k, c)", ["choose", ctx])

    assert result["kind"] == "facts"  # the server warns about a different NAME (P15), not here
