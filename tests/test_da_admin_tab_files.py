"""Fix 11-1, section 14: each tab file loads on its own (no circular import with da_admin_page)."""

import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
TAB_FILES = sorted(p.stem for p in (SRC / "layouts").glob("da_admin_*_tab.py"))


@pytest.mark.parametrize("name", ["da_admin_common", *TAB_FILES])
def test_the_file_imports_alone_in_a_fresh_interpreter(name):
    result = subprocess.run(
        [sys.executable, "-c", f"import layouts.{name}"],
        cwd=SRC,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr


def test_tab_files_never_import_the_page():
    for path in (SRC / "layouts").glob("da_admin_*_tab.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        imports = [line for line in lines if line.startswith(("from ", "import "))]
        assert not [line for line in imports if "da_admin_page" in line], path.name
