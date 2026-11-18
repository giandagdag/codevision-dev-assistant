"""Golden example for the Generator prompt (fix 11-1, AF-21). Plain code picks it, never the AI.

Only the Generator's code prompt gets it: not the Tester, not Understand.
"""

import re

from pydantic_classes.da_rulebook_models import GoldenExample

HEADING = "## Follow this example's style"
MAX_LINES = 80
_RUN_DEF = re.compile(r"^def run\w*", re.MULTILINE)


def program_type_of(path: str, text: str = "") -> str:
    """Screen (layouts/, callbacks/), Batch or ingestion (agents/ with run entry), else Utility."""
    clean = path.replace("\\", "/").lower()
    if "/layouts/" in f"/{clean}" or "/callbacks/" in f"/{clean}":
        return "Screen"
    if "/agents/" in f"/{clean}" and ("__main__" in text or _RUN_DEF.search(text)):
        return "Batch or ingestion"
    return "Utility"


UI_HEADING = "## Screen style: use these brand constants and follow these UI conventions"


def ui_block(brand_constants, rules, path: str, text: str = "") -> str:
    """Screen files only (fix 3, D-F): the brand constants and the UI conventions, each once."""
    if program_type_of(path, text) != "Screen":
        return ""
    brand = [f"- {c.name}: {c.value}" for c in brand_constants]
    conventions = [
        f"- {r.rule_id}: {r.title}. {r.why}".strip() for r in rules if r.kind == "ui_convention"
    ]
    if not brand and not conventions:
        return ""
    parts = [UI_HEADING]
    if brand:
        parts += ["Brand constants:", *brand]
    if conventions:
        parts += ["UI conventions:", *conventions]
    return "\n\n" + "\n".join(parts) + "\n"


def golden_block(examples, path: str, text: str = "") -> str:
    """The first example of the file's type, first 80 lines. Empty when none matches."""
    kind = program_type_of(path, text)
    for example in examples:
        if isinstance(example, GoldenExample) and example.program_type == kind:
            lines = example.code.splitlines()[:MAX_LINES]
            why = f"\n{example.why.strip()}" if example.why.strip() else ""
            return f"\n\n{HEADING}\n{example.title}{why}\n\n" + "\n".join(lines) + "\n"
    return ""
