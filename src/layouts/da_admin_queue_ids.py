"""Button ids of the Review queue (the Unassigned queue). One place, so the catalog tab and the
review view can both build them without importing each other."""

QUEUE_BUTTON_TYPE = "adm-q"
QUEUE_PICK_TYPE = "adm-q-pick"
QUEUE_NOTE_TYPE = "adm-q-note"
QUEUE_BLOCK_ID = "adm-queue"
Q_CONFIRM = "confirm"
Q_MOVE = "move"
Q_APPROVE = "approve"  # take the suggested capability (the id's `cap` carries it)
Q_REJECT = "reject"  # the file belongs in no capability: closes the row as rejected
Q_NEW = "new_capability"  # open the catalog in edit mode with one new row for this file
Q_APPLY = "apply"
Q_APPLY_PATTERN = "apply_pattern"
Q_CANCEL = "cancel"
Q_AI_APPROVE, Q_AI_ASSIGN, Q_AI_REJECT = "ai_approve", "ai_assign", "ai_reject"  # fix 11-2
Q_AI_RETRY = "ai_retry"  # Fix G5 R5: tag one unreadable program again
Q_AI_ALL, Q_AI_ALL_DO = "ai_all", "ai_all_do"  # ask first, then approve every sure proposal
Q_SG_OPEN, Q_SG_SAVE = "sg_open", "sg_save"  # Fix G4 S4: Create and assign (dialog, then save)
Q_SG_ASSIGN, Q_SG_REJECT, Q_SG_REMOVE = "sg_assign", "sg_reject", "sg_remove"
Q_RECHECK = "recheck"  # S6: send the "No capability fits" programs to the AI again
Q_SUGGEST = "suggest_catalog"  # Fix G6 S4: Suggest capabilities from the code
Q_SHOW_RESOLVED ="show_resolved"
Q_HIDE_RESOLVED = "hide_resolved"
# Fix G4 L10: select several at once. The id's `state` says which bulk action.
Q_SELECT_ALL = "select_all"
Q_BULK_ASK, Q_BULK_DO = "bulk_ask", "bulk_do"  # confirm box first, then one version
Q_CLEAR_FILTERS = "clear_filters"
BULK_APPROVE, BULK_ASSIGN, BULK_REJECT = "approve", "assign", "reject"
BULK_PICK_UID = "bulk"  # the id `uid` of the bulk bar's capability picker

# Review queue controls (L7 to L10)
CAT_VIEW_ID = "adm-cat-view"
CAT_PANE_CAPS = "adm-cat-pane-caps"
CAT_PANE_QUEUE = "adm-cat-pane-queue"
VIEW_CAPS, VIEW_QUEUE = "caps", "queue"
RQ_SEARCH_ID = "adm-rq-search"
RQ_SOURCE_ID = "adm-rq-source"
RQ_PROPOSAL_ID = "adm-rq-proposal"
RQ_CONF_ID = "adm-rq-conf"
RQ_FOLDER_ID = "adm-rq-folder"
RQ_SORT_ID = "adm-rq-sort"
RQ_LIST_ID = "adm-rq-list"
RQ_COUNT_ID = "adm-rq-count"
RQ_BAR_ID = "adm-rq-bar"
RQ_SEL_TYPE = "adm-rq-sel"


def queue_button_id(action: str, uid: int | str = 0, cap: str = "", state: str = "") -> dict:
    # Every queue button has the same four keys so one callback pattern matches them all.
    return {"type": QUEUE_BUTTON_TYPE, "action": action, "uid": uid, "cap": cap, "state": state}
