"""Phase 11 fix 3, step 10: UI standards (D-F; AH-14, AH-15, AH-16). Made-up values only."""

from agents import da_build_agent as agent
from agents.da_admin_forms import RESULT_PROBLEMS, RESULT_SAVED, save_from_form
from agents.da_golden_example import UI_HEADING, ui_block
from db_table_functions.db_tbl_da_rulebook import get_active_version
from layouts.da_admin_page import BRAND_NOTE, rules_view
from pydantic_classes.da_rulebook_models import BrandConstant, Rule
from tests.da_build_play import CREATE, make_context

ADMIN = "admin-0001"


def _two_conventions(rulebook):
    def rule(number, title, severity):
        return Rule(
            rule_id=f"CV-UI-{number:03d}", kind="ui_convention", title=title, tags=["look"],
            severity=severity, why="Same look everywhere", good_example="ok", bad_example="no",
            source="Core team",
        )  # fmt: skip

    rules = [rule(901, "Use the brand blue", "should_fix"), rule(902, "Tables have headers", "fyi")]
    old = [r for r in rulebook.rules if r.kind == "ui_convention"]
    rulebook = rulebook.model_copy(update={"rules": [r for r in rulebook.rules if r not in old]})
    return rulebook.model_copy(update={"rules": [*rulebook.rules, *rules]})


def test_ah14_a_brand_value_saves_as_a_new_version_and_the_swatch_follows(
    db_path, published_rulebook
):
    first = published_rulebook.rulebook.brand_constants[0]
    form = {"brand_constants": [{"name": first.name, "value": "#123456", "source": "Core team"}]}

    result = save_from_form(db_path, "ui", form, 1, ADMIN, "New blue")

    assert result.kind == RESULT_SAVED
    saved = get_active_version(db_path)
    assert saved.version_number == 2 and saved.change_note == "New blue"
    changed = {c.name: c.value for c in saved.rulebook.brand_constants}
    assert changed[first.name] == "#123456"
    assert len(saved.rulebook.brand_constants) == len(published_rulebook.rulebook.brand_constants)
    assert "#123456" in str(rules_view("ui", saved))  # the swatch colour


def test_ah14_a_brand_name_cannot_change_and_a_blank_value_is_refused(db_path, published_rulebook):
    first = published_rulebook.rulebook.brand_constants[0]
    renamed = {"brand_constants": [{"name": "OTHER", "value": "#111111", "source": "x"}]}
    save_from_form(db_path, "ui", renamed, 1, ADMIN, "Try rename")  # no row matches: unchanged
    names = [c.name for c in get_active_version(db_path).rulebook.brand_constants]
    assert "OTHER" not in names and first.name in names

    blank = {"brand_constants": [{"name": first.name, "value": "  ", "source": ""}]}
    assert save_from_form(db_path, "ui", blank, 1, ADMIN, "Blank").kind == RESULT_PROBLEMS


def test_the_edit_form_has_value_boxes_and_the_one_line_note(published_rulebook):
    shown = str(rules_view("ui", published_rulebook, editable=True))
    assert "'table': 'brand_constants'" in shown and BRAND_NOTE in shown
    assert BRAND_NOTE in str(rules_view("ui", published_rulebook))


def test_ah15_two_conventions_draw_two_rows_and_the_header_says_two(published_rulebook):
    version = published_rulebook.model_copy(
        update={"rulebook": _two_conventions(published_rulebook.rulebook)}
    )
    shown = str(rules_view("ui", version))

    assert "UI rules: 2" in shown
    assert "CV-UI-901" in shown and "CV-UI-902" in shown
    assert shown.count("Use the brand blue") == 1  # drawn once, not twice


def test_ah16_a_screen_file_prompt_holds_both_lists_once_and_other_files_none(seed_rulebook):
    rulebook = _two_conventions(seed_rulebook)
    base = make_context(rulebook)
    context = agent.BuildContext(
        charter=base.charter, record=base.record, approach=base.approach, cases=base.cases,
        policy=base.policy,
        brand_constants=(BrandConstant(name="PRIMARY_BLUE", value="#0a3d62"),),
        ui_rules=tuple(rulebook.rules),
    )  # fmt: skip
    path = "src/layouts/da_x.py"
    screen = agent.build_code_prompt(context, _contract(), path, "create", 1, "T", "")
    plain = agent.build_code_prompt(context, _contract(), CREATE, "create", 1, "T", "")

    assert screen.count(UI_HEADING) == 1
    assert screen.count("PRIMARY_BLUE: #0a3d62") == 1
    assert screen.count("CV-UI-901: Use the brand blue") == 1
    assert UI_HEADING not in plain


def test_no_lists_means_no_block():
    assert ui_block((), (), "src/layouts/da_x.py") == ""


def _contract():
    import json

    from pydantic_classes.da_build_models import Contract

    return Contract.model_validate(
        json.loads(agent.scripted_build_reply(f"{agent.CONTRACT_MARKER}\n"))
    )
