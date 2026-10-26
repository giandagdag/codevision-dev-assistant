"""A made-up interpreter for tests. Never calls a real AI."""

import json

from agents.da_llm_client import LLMReply


class StubClient:
    """A made-up interpreter for tests: replies come from a queue, prompts are kept for checks.

    Each reply is a dict (sent as JSON) or a str (sent as it is, e.g. to test bad JSON).
    """

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.model = "stub-model"

    def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        if not self.replies:
            raise AssertionError("The stub client ran out of replies.")
        reply = self.replies.pop(0)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return LLMReply(text=text, provider="stub", model=self.model)


def stub_reply(updates=None, ambiguities=None, hint=""):
    """One interpreter reply in the agreed shape."""
    return {"updates": updates or {}, "ambiguities": ambiguities or [], "hint": hint}
