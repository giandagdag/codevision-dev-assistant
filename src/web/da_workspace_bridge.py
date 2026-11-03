"""Connects the browser script to Dash (plan decision P3).

Dash clientside callbacks take JavaScript as text. The Workspace script lives in one file,
da_workspace.js, next to this one. This module reads it and puts it in front of each small
callback body, so the page needs nothing from CodeVision's own `assets` folder. The script
defines `window.daWorkspace` only once, however many callbacks carry it.
"""

from functools import lru_cache
from pathlib import Path

SCRIPT_FILE = Path(__file__).with_name("da_workspace.js")


@lru_cache(maxsize=1)
def workspace_script() -> str:
    """The whole browser script as text."""
    return SCRIPT_FILE.read_text(encoding="utf-8")


def clientside_function(arguments: str, body: str) -> str:
    """A Dash clientside callback: `function(arguments) { <script> body }`."""
    return f"function({arguments}) {{\n{workspace_script()}\n{body}\n}}"
