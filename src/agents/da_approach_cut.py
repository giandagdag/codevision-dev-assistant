"""Cut over-long text in the Generator's reply before it is checked (Fix G7, L1, L2).

Length is formatting, not a rule: a good plan is never thrown away because a sentence is a few
characters too long. Each over-long field is cut at a word with "…", and the uncut text (up to
1,000 characters) is kept in `full_text` so the screen can show it on hover. Count limits
(files, design choices, libraries) are rules and stay checks.
"""

from pydantic_classes.da_approach_models import (
    OPTION_LIMIT,
    SUMMARY_LIMIT,
    TEXT_LIMIT,
)
from pydantic_classes.da_approach_text import (
    FULL_TEXT_LIMIT,
    LABEL_LIMIT,
    cut_text,
    make_label,
    unique_labels,
)


def _cut_field(holder: dict, key: str, limit: int, store: dict, store_key: str) -> None:
    """Cut holder[key] when it is a string over `limit`; keep the uncut text in `store`."""
    value = holder.get(key)
    if isinstance(value, str) and len(value.strip()) > limit:
        store[store_key] = value.strip()[:FULL_TEXT_LIMIT]
        holder[key] = cut_text(value, limit)


def _each(data: dict, key: str):
    """The dict items of a list field (anything else is left for the shape check to refuse)."""
    items = data.get(key)
    return enumerate(items) if isinstance(items, list) else ()


def _cut_option_list(choice: dict) -> None:
    """Options may be plain strings or {"label", "detail"}. The result: `options` are the full
    texts and `labels` the short button texts."""
    options = choice.get("options")
    if not isinstance(options, list) or not all(isinstance(o, str | dict) for o in options):
        return
    store = choice["full_text"]
    details, labels = [], []
    for number, option in enumerate(options, start=1):
        label = option.get("label") if isinstance(option, dict) else None
        detail = option.get("detail") if isinstance(option, dict) else option
        if not isinstance(detail, str) or not detail.strip():
            detail = label  # a label alone is the whole text
        if not isinstance(detail, str):
            return  # not usable: the shape check says so
        holder = {"detail": detail}
        _cut_field(holder, "detail", OPTION_LIMIT, store, f"option_{number}")
        details.append(holder["detail"])
        labels.append(
            cut_text(label, LABEL_LIMIT)
            if isinstance(label, str) and label.strip()
            else make_label(holder["detail"])
        )
    choice["options"] = details
    choice["labels"] = unique_labels(labels)


def cut_reply(data):
    """The reply data with over-long text cut. Anything that is not the expected shape is
    returned untouched for the shape check. The AI cannot set the app's own fields."""
    if not isinstance(data, dict):
        return data
    data = dict(data)
    data["full_text"] = full = {}
    data.pop("labels", None)
    _cut_field(data, "summary", SUMMARY_LIMIT, full, "summary")
    for key, field, prefix in (
        ("files", "purpose", "purpose"),
        ("needs_people", "reason", "need_reason"),
        ("reuse_decisions", "reason", "reuse_reason"),
    ):
        data[key] = _copy_items(data, key)
        for number, item in _each(data, key):
            if isinstance(item, dict):
                _cut_field(item, field, TEXT_LIMIT, full, f"{prefix}_{number}")
    data["design_choices"] = _copy_items(data, "design_choices")
    for _number, choice in _each(data, "design_choices"):
        if not isinstance(choice, dict):
            continue
        choice.pop("labels", None)
        choice["full_text"] = {}
        _cut_field(choice, "question", TEXT_LIMIT, choice["full_text"], "question")
        _cut_field(choice, "impact", TEXT_LIMIT, choice["full_text"], "impact")
        _cut_option_list(choice)
    return data


def _copy_items(data: dict, key: str):
    """A copy of a list of dicts, so the caller's reply data is never changed in place."""
    items = data.get(key, [])
    if not isinstance(items, list):
        return items
    return [dict(item) if isinstance(item, dict) else item for item in items]


def was_cut(reply) -> bool:
    """True when the app cut some text of this reply (the retry note then asks for shorter)."""
    return bool(reply.full_text) or any(choice.full_text for choice in reply.design_choices)
