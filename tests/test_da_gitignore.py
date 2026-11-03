"""Test 5-29 (P25): .vscode/ is ignored by Git."""

from pathlib import Path

GITIGNORE = Path(__file__).resolve().parent.parent / ".gitignore"


def test_gitignore_lists_the_vscode_folder():
    lines = [line.strip() for line in GITIGNORE.read_text(encoding="utf-8").splitlines()]

    assert ".vscode/" in lines
