"""G9-21 (AF-2): the new G9 screen words hold no raw field or setting names (DA_..., etc.).

The words come from constants, so the scan reads the constants and the lines built from them."""

from agents import da_understand_rules as rules
from agents.da_admin_labels import raw_names_in
from agents.da_handoff_screen import CHECK_FOLDER_HINT
from agents.da_refine_screen import RESCAN_HINT
from agents.da_rule_check_agent import COULD_NOT_RUN
from agents.da_rule_exception_actions import APPROVE_LABEL, REJECT_LABEL
from layouts import da_tester_panel as tp
from layouts.da_admin_catalog_tab import MISSING_CHIP_LABEL
from pydantic_classes.da_rule_conflict_models import RuleConflict
from tests.test_da_admin_label_scan import CODE_NAMES


def test_g9_21_the_new_screen_words_show_no_raw_names():
    conflict = RuleConflict(
        criterion="AC-2",
        rule="CV-PY-001",
        title="Return, never raise",
        why="The criterion asks the code to raise an error",
        fix="Return the text INVALID PASSWORD",
    )
    lines = [
        *rules.conflict_lines([conflict]),
        rules.USE_WORDING_PREFIX,
        rules.CHANGE_MYSELF_PREFIX,
        rules.ASK_EXCEPTION_PREFIX,
        rules.EXCEPTION_NEEDS_REASON,
        rules.CHANGE_MYSELF_MESSAGE,
        rules.NO_WORDING_MESSAGE,
        rules.TRY_AGAIN_OPTION,
        COULD_NOT_RUN,
        APPROVE_LABEL,
        REJECT_LABEL,
        RESCAN_HINT,
        CHECK_FOLDER_HINT,
        MISSING_CHIP_LABEL,
        tp.SEE_FINDINGS_TEXT,
        *tp.FINDING_CHECK_NAMES.values(),
    ]

    assert not [line for line in lines if raw_names_in(line, CODE_NAMES)]
