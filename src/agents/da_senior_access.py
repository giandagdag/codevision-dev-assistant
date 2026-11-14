"""Who may open the senior inbox (Phase 10 spec section 9, work fact WF-1).

A switch like the Admin one: at home `DA_SENIOR_IDS` plus every named or backup senior in the
ACTIVE catalog decide; at work the real source is not decided yet, so "codevision" lets nobody in
and says why in the log.
"""

from configs.da_config import Settings
from da_logging import get_logger
from db_table_functions.db_tbl_da_rulebook import get_active_version

logger = get_logger(__name__)

NOT_SENIOR_MESSAGE = "This page is for capability seniors."
NOT_CONFIGURED_LINE = "Senior access is not configured yet (DA_SENIOR_SOURCE=codevision)."


def catalog_senior_labels(settings: Settings) -> set[str]:
    """Every named and backup senior in the active rulebook version (home: the label is the ID)."""
    active = get_active_version(settings.db_path)
    if active is None:
        return set()
    labels = set()
    for capability in active.rulebook.policy.capabilities:
        labels.update(x.strip() for x in (capability.named_senior, capability.backup_senior) if x)
    return {label for label in labels if label}


def is_senior(settings: Settings, user_id: str) -> bool:
    if settings.senior_source == "codevision":
        logger.warning(NOT_CONFIGURED_LINE)
        return False
    who = (user_id or "").strip()
    if not who:
        return False
    return who in settings.senior_ids or who in catalog_senior_labels(settings)
