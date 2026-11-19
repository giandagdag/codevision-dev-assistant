"""Fix NP step 1: a test file that cannot load is named, not counted as "Not proven".

Real subprocesses on the made-up CodeVision-shaped fixture. No AI, no internet."""

from pathlib import Path

from agents.da_sandbox import NOT_RUN_MESSAGE, run_tests

REFERENCE = Path(__file__).parent / "fixtures" / "da_reference_codevision"
EXCLUDE = [".env", "*.db", ".git", "*.key", "*.pem"]


def run(test_text):
    return run_tests(
        REFERENCE, {}, "cvda_np", test_text, exclude=EXCLUDE, timeout_seconds=20
    )


def methods(count):
    return "".join(
        f'    def test_t{n}_ac{n}_x(self):\n        """X."""\n        self.assertTrue(True)\n'
        for n in range(count)
    )


def test_a_missing_library_is_one_load_error_and_the_tests_did_not_run():
    """NP-1 (sandbox part): 6 frozen tests, the file imports a module the sandbox lacks."""
    text = (
        "import unittest\nimport openpyxl_not_installed\n\n\n"
        "class C(unittest.TestCase):\n" + methods(6)
    )

    result = run(text)

    assert result.load_error is not None
    assert result.load_error.kind == "import"
    assert result.load_error.error_type == "ModuleNotFoundError"
    assert "openpyxl_not_installed" in result.load_error.message
    assert len(result.tests) == 6  # the stand-in row is not a test
    assert {t.result for t in result.tests} == {"not_run"}
    assert all(t.message == NOT_RUN_MESSAGE for t in result.tests)
    assert result.not_proven == []
    assert result.ran_count == 0
    assert not result.ok


def test_a_set_up_class_that_raises_is_a_load_error():
    """NP-3 (sandbox part)."""
    text = (
        "import unittest\n\n\nclass C(unittest.TestCase):\n"
        "    @classmethod\n    def setUpClass(cls):\n        raise RuntimeError('no data file')\n\n"
        + methods(2)
    )

    result = run(text)

    assert result.load_error is not None
    assert result.load_error.kind == "set_up"
    assert "no data file" in result.load_error.message
    assert {t.result for t in result.tests} == {"not_run"}
    assert not result.ok


def test_a_tear_down_class_failure_keeps_the_real_rows():
    text = (
        "import unittest\n\n\nclass C(unittest.TestCase):\n"
        "    @classmethod\n    def tearDownClass(cls):\n        raise RuntimeError('cleanup')\n\n"
        + methods(2)
    )

    result = run(text)

    assert result.load_error is not None and "cleanup" in result.load_error.message
    assert result.passed == 2  # they really ran and passed before the tear-down broke
    assert not any(t.result == "not_run" for t in result.tests)
    assert not result.ok


def test_a_clean_file_has_no_load_error_and_still_passes():
    text = "import unittest\n\n\nclass C(unittest.TestCase):\n" + methods(2)

    result = run(text)

    assert result.load_error is None and result.ok and result.ran_count == 2
