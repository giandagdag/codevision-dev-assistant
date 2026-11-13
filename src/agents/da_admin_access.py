"""Who may open the Admin console (spec section 3, work fact WF-2).

Built as a switch, like DA_SEARCH_PROVIDER: at home the list in DA_ADMIN_IDS decides; at work the
real source (a CodeVision role or group) is not decided yet, so "codevision" lets nobody in and
says why in the log. An empty list means nobody is Admin.
"""

from configs.da_config import Settings
from da_logging import get_logger

logger = get_logger(__name__)

NOT_ADMIN_MESSAGE = "This page is for the CodeVision core team."


def is_admin(settings: Settings, user_id: str) -> bool:
    if settings.admin_source == "codevision":
        logger.warning("Admin access is not configured yet (DA_ADMIN_SOURCE=codevision).")
        return False
    return bool(user_id) and user_id.strip() in settings.admin_ids
