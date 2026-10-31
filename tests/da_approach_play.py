"""Test helpers for Approach: a request at DISCOVERY_CONFIRMED, and quick ways to reach each step.

Everything uses the fake provider's scripted replies, so no test calls a real AI.
"""

import json
from datetime import UTC, datetime

from agents import da_approach_flow as flow
from agents.da_approach_agent import ScriptedApproachClient
from agents.da_discover_flow import confirm_discovery, start_discovery
from agents.da_llm_client import LLMReply
from agents.da_tester_agent import ScriptedTesterClient
from db_table_functions.db_tbl_da_audit import list_audit_events
from tests.da_play import to_confirmed

T0 = datetime(2026, 10, 31, 9, 0, tzinfo=UTC)


class Tweaked:
    """The scripted Generator reply for one call, changed by a function before it is returned.
    Counts how many times it was asked."""

    model = "tweaked-script"

    def __init__(self, call, change=None):
        self.call = call
        self.change = change
        self.prompts: list[str] = []

    def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        reply = ScriptedApproachClient(self.call).complete(prompt)
        data = json.loads(reply.text)
        if self.change:
            self.change(data)
        return LLMReply(text=json.dumps(data), provider="fake", model=self.model)


class ChangedTester:
    """The scripted Tester reply for one step, changed by a function. Keeps the prompts."""

    model = "tweaked-tester"

    def __init__(self, step, change=None):
        self.step = step
        self.change = change
        self.prompts: list[str] = []

    def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        data = json.loads(ScriptedTesterClient(self.step).complete(prompt).text)
        if self.change:
            self.change(data)
        return LLMReply(text=json.dumps(data), provider="fake", model=self.model)


def discovery_confirmed_id(settings) -> str:
    request_id = to_confirmed(settings).request.request_id
    view = start_discovery(settings, request_id, 0)
    confirm_discovery(settings, request_id, view.revision)
    return request_id


def event_types(settings, request_id) -> list[str]:
    return [e.event_type for e in list_audit_events(settings.db_path, request_id)]


def events_of(settings, request_id, event_type):
    events = list_audit_events(settings.db_path, request_id)
    return [e for e in events if e.event_type == event_type]


def texts(view, speaker=None) -> list[str]:
    return [m.text for m in view.messages if speaker is None or m.speaker == speaker]


def proposed(settings, request_id, change=None):
    """After Proceed to Approach: step choices (the scripted plan has one design choice)."""
    return flow.start_approach(settings, request_id, 0, generator=Tweaked("propose", change))


def at_review(settings, request_id):
    """The design choice answered by its first button: the settled plan, step review."""
    view = proposed(settings, request_id)
    option = view.buttons[0][1]
    return flow.choose_design_option(
        settings, request_id, option, view.revision, generator=ScriptedApproachClient("settle")
    )


def at_tests(settings, request_id):
    """Approach accepted and the Tester's plan written: step tests."""
    view = at_review(settings, request_id)
    return flow.accept_approach(
        settings, request_id, view.revision, tester=ScriptedTesterClient("test_plan")
    )
