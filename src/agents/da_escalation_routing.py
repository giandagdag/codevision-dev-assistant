"""Who gets an escalation (Phase 10 spec section 8). Plain code: the AI never routes.

The catalog is the ACTIVE rulebook's (a senior who left should not keep getting escalations,
D-J), so callers pass `active.rulebook.policy.capabilities`, not the request's pinned copy.
"""

from agents.da_enhance_checks import lookup_capability
from pydantic_classes.da_escalation_models import UNASSIGNED, Route
from pydantic_classes.da_rulebook_models import Capability


def route_for(
    capabilities: list[Capability], capability_name: str, planned_paths: list[str]
) -> Route:
    """Pick the capability, then its named senior, then the backup, else Unassigned.

    `capability_name` is the confirmed target's capability (enhancement). Without one, the
    catalog lookup on the planned files decides: the first planned file's capability is used and
    the others are listed on the row."""
    found = _by_name(capabilities, capability_name)
    others: list[str] = []
    if found is None:
        matches = [c for c in (lookup_capability(p, capabilities) for p in planned_paths) if c]
        if matches:
            found = matches[0]
            others = _unique_names(matches[1:], skip=found.name)
    if found is None:
        return Route()
    return _route_of(found, others)


def _by_name(capabilities: list[Capability], name: str) -> Capability | None:
    if not name:
        return None
    return next((c for c in capabilities if c.name == name), None)


def _unique_names(items: list[Capability], skip: str) -> list[str]:
    names: list[str] = []
    for item in items:
        if item.name != skip and item.name not in names:
            names.append(item.name)
    return names


def _route_of(capability: Capability, others: list[str]) -> Route:
    named = capability.named_senior.strip()
    backup = capability.backup_senior.strip()
    senior = named or backup or UNASSIGNED
    return Route(
        capability=capability.name,
        other_capabilities=others,
        senior_label=senior,
        backup_label=backup if senior != backup else "",
    )


def is_unassigned(senior_label: str) -> bool:
    return senior_label == UNASSIGNED


def matches_senior(senior_label: str, backup_label: str, user_id: str) -> bool:
    """Spec section 8 step 3: a row shows to a user whose ID matches either label. At home the
    label is the ID (D-G). Unassigned rows show to every senior."""
    who = user_id.strip()
    return is_unassigned(senior_label) or who in (senior_label, backup_label)
