"""Test helpers: look inside a tree of Dash components without a browser."""

from collections.abc import Iterator


def walk(node) -> Iterator:
    """Every component and every string in the tree, parents first."""
    yield node
    if isinstance(node, list | tuple):
        for child in node:
            yield from walk(child)
    elif hasattr(node, "children"):
        yield from walk(node.children)
    # Components can also carry components in other props (e.g. label, leftSection).
    for name in ("label", "leftSection", "rightSection"):
        extra = getattr(node, name, None)
        if extra is not None and not isinstance(extra, str):
            yield from walk(extra)


def texts(node) -> list[str]:
    return [item for item in walk(node) if isinstance(item, str)]


def all_text(node) -> str:
    return "\n".join(texts(node))


def components(node, kind: str | None = None) -> list:
    found = [item for item in walk(node) if hasattr(item, "_type")]
    return [item for item in found if kind is None or item._type == kind]


def by_id(node, component_id):
    matches = [item for item in components(node) if getattr(item, "id", None) == component_id]
    return matches[0] if matches else None
