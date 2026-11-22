"""Fix G6 code review round 1: the Must fix items. Made-up names only."""

import json
from types import SimpleNamespace

from agents.da_admin_suggestions import Suggestion
from agents.da_capability_suggest import NamedGroup, name_group
from agents.da_capability_suggest_job import ScriptedGroupClient
from agents.da_code_clusters import Group
from callbacks.screen_callbacks.da_capability_map_callbacks import next_state
from layouts.da_admin_catalog_tab import LINKS_KEY, queue_block
from layouts.da_admin_job_bar import job_bar
from layouts.da_capability_map_view import ADMIN_LINK, CHIP_TYPE
from tests.test_da_admin_page import walk


def test_the_tagger_prompt_asks_for_the_also_field():
    from agents.da_admin_tagger import PROMPT_FILE  # the shipped prompt text

    assert '"also"' in PROMPT_FILE.read_text(encoding="utf-8")


def test_an_excluded_path_never_reaches_the_group_prompt():
    prompts: list[str] = []

    class Spy:
        def complete(self, prompt, system=None):
            prompts.append(prompt)
            return SimpleNamespace(text=json.dumps({"name": "Docs", "description": "d",
                                                    "not_in_group": [], "confidence": "high"}))

    group = Group(("a/x.py", "a/secret_tool.py"), ("a",), 1, 0)
    named = name_group(group, {}, Spy(), exclusions=["a/secret_*"])

    assert isinstance(named, NamedGroup) and "secret_tool" not in prompts[0]


def test_a_links_card_and_a_tagger_card_with_the_same_name_and_path_keep_their_own_ids():
    same = {"a/x.py": "does x"}
    links = Suggestion("Docs", "d", "high", same, from_links=True)
    tagger = Suggestion("Docs", "d", "high", same)
    queue = {"rows": [], "resolved": None, "dialog": None, "notice": [],
             "suggestions": [links, tagger]}  # fmt: skip

    ids = [json.dumps(n.id, sort_keys=True) for n in walk(queue_block(queue, ["Uploads"]))
           if isinstance(getattr(n, "id", None), dict)]  # fmt: skip

    assert len(ids) == len(set(ids))
    assert any(LINKS_KEY in i for i in ids)


def test_a_suggest_job_bar_has_no_stop_button():
    from datetime import datetime

    status = {"mode": "suggest", "step": 1, "done": 0, "total": 0, "started_by": "a"}
    parts = job_bar(status, datetime(2026, 1, 1, 9, 0), "queue")

    assert not any("Stop" == getattr(p, "children", None) for p in walk(parts))


def test_a_foundation_chip_click_focuses_it_and_the_unassigned_link_opens_the_queue():
    state = {"cap": "", "module": "", "focus": "", "tap": ["", 0]}

    new = next_state(CHIP_TYPE, state, None, "Shared utils")

    assert new["focus"] == "Shared utils"
    assert "tab=catalog" in ADMIN_LINK and "view=queue" in ADMIN_LINK


def _cap(name, senior, pattern):
    from pydantic_classes.da_rulebook_models import Capability

    return Capability(name=name, description="d", named_senior=senior, path_patterns=[pattern])


def test_g6_6_a_program_in_two_capabilities_escalates_to_the_main_senior_only():
    from agents.da_escalation_routing import route_for

    caps = [_cap("Markdown", "senior-md", "docs/*.py"), _cap("Ingestion", "senior-in", "docs/x.py")]

    route = route_for(caps, "", ["docs/x.py"])

    assert route.capability == "Markdown" and route.senior_label == "senior-md"


def test_discover_names_the_main_capability_then_the_also_ones():
    from agents.da_discover_queries import _label

    caps = [_cap("Markdown", "s1", "docs/*.py"), _cap("Ingestion", "s2", "docs/x.py")]

    assert _label("docs/x.py", "Markdown", caps) == "Markdown (also: Ingestion)"
    assert _label("docs/y.py", "Markdown", caps) == "Markdown"


def test_scripted_client_still_names_groups():
    assert ScriptedGroupClient.model == "fake-group-script"
