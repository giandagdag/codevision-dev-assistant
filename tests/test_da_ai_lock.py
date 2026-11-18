from datetime import UTC, datetime, timedelta

import dash_mantine_components as dmc
import pytest

from agents import da_ai_lock
from agents.da_ai_lock import BUSY_MESSAGE, TIME_LIMIT, AiBusyError, ai_turn
from callbacks.screen_callbacks.da_developer_assistant_page_callbacks import (
    perform_action,
    perform_finding_action,
    perform_form,
)
from layouts.da_lock_buttons import lock_buttons

RID = "CVDA-2026-0001"
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clean_lock():
    da_ai_lock._held.clear()
    yield
    da_ai_lock._held.clear()


def test_second_start_is_refused_and_finish_frees_it():
    assert da_ai_lock.try_start(RID, NOW)
    assert not da_ai_lock.try_start(RID, NOW)
    da_ai_lock.finish(RID)
    assert da_ai_lock.try_start(RID, NOW)


def test_a_stuck_entry_clears_after_the_time_limit():
    da_ai_lock.try_start(RID, NOW)
    assert da_ai_lock.is_busy(RID, NOW + TIME_LIMIT - timedelta(seconds=1))
    assert da_ai_lock.try_start(RID, NOW + TIME_LIMIT)


def test_lock_is_released_when_the_ai_call_raises():
    with pytest.raises(RuntimeError), ai_turn(RID):
        raise RuntimeError("AI down")
    assert not da_ai_lock.is_busy(RID)


def test_a_forced_second_call_is_refused_with_a_plain_message():
    with ai_turn(RID):
        with pytest.raises(AiBusyError, match="still working"):
            with ai_turn(RID):
                pass
        state = {"request_id": RID}
        assert perform_action(None, None, "", state, 1)[2] == BUSY_MESSAGE
        assert perform_form(None, [], state, 1)[1] == BUSY_MESSAGE
        assert perform_finding_action(None, "accept:F-1", {}, state, 1)[1] == BUSY_MESSAGE


def test_busy_page_disables_buttons_except_the_stop_buttons():
    tree = dmc.Stack(
        [
            dmc.Button("Send", id="a"),
            dmc.Group([dmc.Button("Cancel build", id="b"), dmc.Button("Cancel test", id="c")]),
            dmc.Paper(dmc.Button("Proceed", id="d")),
        ]
    )
    lock_buttons(tree)
    flags = {b.id: getattr(b, "disabled", None) for b in _buttons(tree)}
    assert flags == {"a": True, "b": None, "c": None, "d": True}


def _buttons(component):
    if not hasattr(component, "children"):
        return []
    found = [component] if isinstance(component, dmc.Button) else []
    children = getattr(component, "children", None)
    for part in children if isinstance(children, list) else [children]:
        found += _buttons(part)
    return found
