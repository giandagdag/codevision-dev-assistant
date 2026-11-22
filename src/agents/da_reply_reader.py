"""Fix G5 R1: one forgiving reader for AI replies that should hold a JSON object.

Models wrap the JSON in words, code fences or a <think> block. This takes the first balanced
{...} object that parses, wherever it sits, and ignores everything around it.
"""

import json
import re

from agents.da_understand_agent import strip_think_block

_THINK_ANYWHERE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def read_json_object(text: str) -> dict | None:
    """The first JSON object in the text, or None. Never raises."""
    cleaned = strip_think_block(_THINK_ANYWHERE.sub("", text or ""))
    start = cleaned.find("{")
    while start != -1:
        end = _balanced_end(cleaned, start)
        if end is not None:
            try:
                data = json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                return data
        start = cleaned.find("{", start + 1)
    return None


def _balanced_end(text: str, start: int) -> int | None:
    """Index just after the brace that closes the one at start (braces in strings are skipped)."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None
