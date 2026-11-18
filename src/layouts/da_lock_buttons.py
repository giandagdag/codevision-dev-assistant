"""Lock every action button while a request waits on the AI (B2 S5).

One walk over the drawn page, so no screen needs its own rule. The stop buttons stay usable:
a person must always be able to cancel a build or a test.
"""

import dash_mantine_components as dmc

ALLOWED_LABELS = ("Cancel build", "Cancel test")  # Home is a link, not a button


def lock_buttons(component) -> None:
    """Set disabled=True on every dmc.Button under `component`, except the stop buttons."""
    if component is None or isinstance(component, (str, int, float)):
        return
    if isinstance(component, (list, tuple)):
        for part in component:
            lock_buttons(part)
        return
    if isinstance(component, dmc.Button) and component.children not in ALLOWED_LABELS:
        component.disabled = True
    lock_buttons(getattr(component, "children", None))
