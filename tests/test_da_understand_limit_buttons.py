"""B2 step 4 (S7c, S7e): the buttons at the decision limit and the never-assume list."""

import pytest

from agents.da_understand_checks import is_never_assumed
from agents.da_understand_flow import (
    ASSUME_OPTION,
    SEND_SENIOR_OPTION,
    choose_option,
)
from db_table_functions.db_tbl_da_understand import UnderstandError
from tests.da_stub_client import StubClient, stub_reply
from tests.test_da_understand_flow import GOOD_Q1, answer, choose, limit_five, start

pytestmark = pytest.mark.usefixtures("published_rulebook", "limit_five")

# Same fixtures as the Understand flow tests: the limit is 5 so the screen reaches it quickly.
limit_five = limit_five  # noqa: PLW0127


@pytest.fixture
def settings(make_settings):
    return make_settings()


def ask(text):
    return {"text": text, "material": True, "options": ["Yes", "No"]}


def at_limit(settings, last_question):
    """Five decisions answered, then one more open decision: the screen is at the limit."""
    view = start(settings)
    five = [ask(f"Decision {n}?") for n in range(5)]
    view = answer(settings, view, client=StubClient(stub_reply(GOOD_Q1["updates"], five)))
    for _ in range(5):
        view = choose(settings, view, "Yes")
    return answer(settings, view, client=StubClient(stub_reply({}, [ask(last_question)])))


def test_keyword_list():
    assert is_never_assumed("Should the Customer see the balance?")
    assert not is_never_assumed("Should hidden worksheets be read?")


def test_limit_offers_both_buttons_and_proceed_continues(settings):
    view = at_limit(settings, "Should hidden sheets be read?")

    assert view.input_mode == "waiting"
    assert view.choices == [ASSUME_OPTION, SEND_SENIOR_OPTION]

    view = choose(settings, view, ASSUME_OPTION)

    assert view.record.open_items == []
    assert view.choices == []
    assert view.input_mode != "waiting"


def test_customer_decision_is_never_assumed(settings):
    view = at_limit(settings, "Should the customer account number be shown?")

    assert view.choices == [SEND_SENIOR_OPTION]
    with pytest.raises(UnderstandError, match="not one of the choices"):
        choose(settings, view, ASSUME_OPTION)


def test_proceed_leaves_the_sensitive_one_blocking(settings):
    view = start(settings)
    five = [ask(f"Decision {n}?") for n in range(5)]
    view = answer(settings, view, client=StubClient(stub_reply(GOOD_Q1["updates"], five)))
    for _ in range(5):
        view = choose(settings, view, "Yes")
    more = [ask("Should hidden sheets be read?"), ask("Is the payment amount rounded?")]
    view = answer(settings, view, client=StubClient(stub_reply({}, more)))

    view = choose(settings, view, ASSUME_OPTION)

    assert view.record.open_items == ["Needs a senior decision: Is the payment amount rounded?"]
    assert view.choices == [SEND_SENIOR_OPTION]


def test_send_to_senior_opens_an_escalation(settings):
    view = at_limit(settings, "Should the customer account number be shown?")

    view = choose_option(
        settings, view.request.request_id, SEND_SENIOR_OPTION, view.revision
    )

    assert view.request.status == "ESCALATION_REQUIRED"
