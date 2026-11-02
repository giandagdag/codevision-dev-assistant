"""The browser script in a real browser (Phase 5 step 10).

Rows 5-15 (same fingerprint as Python), 5-16 (line endings kept on disk), 5-11 and 5-12/5-13
(browser half of the path rules and the edit guard), 5-18 and 5-24 (nothing outside the plan and
the tests folder is read), 5-23 (the ZIP). Skipped, not failed, when Playwright is missing.
"""

import zipfile

import pytest

from agents.da_workspace_checks import fingerprint
from tests.da_browser import HAS_DIR_JS, READ_JS, SEED_JS

TESTS = "tests/cvda_2026_0001"
CTX = {
    "planned_paths": ["src/agents/excel_processor.py", "src/agents/upload_validator.py"],
    "markers": ["src/web", "src/callbacks"],
    "max_file_kb": 512,
    "tests_folder": TESTS + "/",
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


def job(page, items, creatable=("tests", TESTS)):
    return {
        "request_id": "CVDA-2026-0001",
        "folder_name": "x",
        "creatable_folders": list(creatable),
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


def test_5_18_and_5_24_files_outside_the_plan_and_tests_folder_are_never_opened(make_page):
    page = make_page()
    extra = {f"{TESTS}/__init__.py": "# x\n", f"{TESTS}/test_mine.py": "pass\n"}
    page.evaluate(SEED_JS, {**TREE, **extra})

    result = pick(page)

    opened = set(page.evaluate("() => window.__opened"))
    assert opened == {"upload_validator.py", "__init__.py", "test_mine.py"}
    assert "secret_notes.py" not in opened and "README.md" not in opened
    names = sorted(f["name"] for f in result["facts"]["tests_files"])
    assert names == ["__init__.py", "test_mine.py"]


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


def test_the_job_creates_the_tests_folder_and_reads_the_file_back(make_page):
    page = make_page()
    page.evaluate(SEED_JS, TREE)
    pick(page)
    text = "# Tests for this request\n"

    report = run(page, job(page, [(f"{TESTS}/__init__.py", text, "absent")]))

    assert report["stopped"] is None
    assert report["written"] == [
        {"path": f"{TESTS}/__init__.py", "text": text, "fingerprint": fingerprint(text)}
    ]
    assert page.evaluate(READ_JS, f"{TESTS}/__init__.py") == text


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
        (f"{TESTS}/__init__.py", "# a\n", "absent"),
        ("src/agents/upload_validator.py", "generated\n", fingerprint("original\n")),
        (f"{TESTS}/test_c.py", "# c\n", "absent"),
    ]

    report = run(page, job(page, items))

    assert [w["path"] for w in report["written"]] == [f"{TESTS}/__init__.py"]
    assert report["stopped"]["path"] == "src/agents/upload_validator.py"
    assert "Re-scan first" in report["stopped"]["reason"]
    assert page.evaluate(READ_JS, "src/agents/upload_validator.py") == "developer edit\n"
    assert page.evaluate(READ_JS, f"{TESTS}/test_c.py") is None
    assert page.evaluate(READ_JS, f"{TESTS}/__init__.py") == "# a\n"


def test_5_13_a_new_file_that_already_exists_is_stopped(make_page):
    page = make_page()
    page.evaluate(SEED_JS, {**TREE, f"{TESTS}/__init__.py": "somebody was here\n"})
    pick(page)

    report = run(page, job(page, [(f"{TESTS}/__init__.py", "# mine\n", "absent")]))

    assert "already exists" in report["stopped"]["reason"]
    assert page.evaluate(READ_JS, f"{TESTS}/__init__.py") == "somebody was here\n"


# --- 5-23 and 5-24: the fallback ---


def test_5_23_download_zip_holds_the_tests_file_and_the_readme(make_page, tmp_path):
    page = make_page()
    pack = {
        "files": [{"path": f"{TESTS}/__init__.py", "text": "# Tests\n"}],
        "readme_name": "READ_ME_FIRST.txt",
        "readme": "Unzip this file into your CodeVision folder.\r\n",
    }

    with page.expect_download() as info:
        page.evaluate("(p) => window.daWorkspace.download(p)", pack)
    target = tmp_path / "pack.zip"
    info.value.save_as(target)

    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None  # every CRC is right
        assert sorted(archive.namelist()) == sorted([f"{TESTS}/__init__.py", "READ_ME_FIRST.txt"])
        assert archive.read(f"{TESTS}/__init__.py").decode() == "# Tests\n"
        assert b"Unzip this file" in archive.read("READ_ME_FIRST.txt")


def test_5_24_upload_sends_only_planned_and_tests_files(make_page, tmp_path):
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
    assert opened == {
        "codevision/src/agents/upload_validator.py",
        f"codevision/{TESTS}/test_mine.py",
    }
    assert [f["name"] for f in facts["tests_files"]] == ["test_mine.py"]
