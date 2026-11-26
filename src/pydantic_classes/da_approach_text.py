"""Cutting long text for Approach (Fix G7, L2): cut at a word, never reject for length."""

ELLIPSIS = "…"
LABEL_LIMIT = 60
DETAIL_LIMIT = 300
FULL_TEXT_LIMIT = 1000


def cut_text(text: str, limit: int) -> str:
    """The text itself when it fits, else cut at a word boundary to `limit` with an ellipsis."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[: limit - len(ELLIPSIS)]
    # Mid-word: go back to the last space so no word is split. One huge word is cut hard.
    if not text[len(head)].isspace() and " " in head:
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(" ,;:.-") + ELLIPSIS


def make_label(detail: str) -> str:
    """A button label from a full option text: its first words, up to LABEL_LIMIT."""
    return cut_text(detail, LABEL_LIMIT)


def unique_labels(labels: list[str]) -> list[str]:
    """Two options may start with the same words: the later ones get " (2)", " (3)" so the
    developer can tell the buttons apart."""
    seen: dict[str, int] = {}
    result = []
    for label in labels:
        count = seen.get(label, 0) + 1
        seen[label] = count
        if count == 1:
            result.append(label)
        else:
            suffix = f" ({count})"
            result.append(cut_text(label, LABEL_LIMIT - len(suffix)) + suffix)
    return result
