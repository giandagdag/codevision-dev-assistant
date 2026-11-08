"""Row 8-42: build, edit one line in the private test folder, Re-scan, Check my edits, a bug lane
and a rebuild, in a real browser. His edited line must still be in the file at the end.

SKIPPED for now, on purpose. The Refine box is drawn (steps 13a to 13d), but its buttons have no
click callbacks yet, so a browser cannot press Refine, a lane, Re-scan or Check my edits. The
engine behind each button is tested without a browser (`test_da_refine_*.py`, the smoke check items
27 and 28). When the callbacks exist, fill in the body below and remove the skip.
"""

import pytest

pytestmark = pytest.mark.usefixtures("published_rulebook")

STEPS = (
    "build and write to the browser's private test folder",
    "edit one line of a planned file in that folder",
    "click Re-scan: the side-by-side shows the edit",
    "click Check my edits: green",
    "type a bug, pick the bug lane, confirm the repro, rebuild",
    "read the file back: his edited line is still there",
)


@pytest.mark.skip(reason="Phase 8 buttons are drawn but not wired to callbacks yet (see docstring)")
def test_8_42_his_edit_survives_a_bug_lane_rebuild_in_a_real_browser():
    raise AssertionError("not written yet: " + "; ".join(STEPS))
