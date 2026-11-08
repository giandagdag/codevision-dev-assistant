"""Plain-code rules for Refine (Phase 8). No AI, no database: every rule can be tested with
made-up values.

Part 1 (this part): the record side. Apply the AI's change-only reply to a copy of the record,
number new criteria so an ID is never reused, diff two versions, and check the lane suggestion.
Part 2 (further down): the code side, his lines and conflicts.

AS400 picture: amending a signed change request. The form gets revision 2, same request number;
lines nobody touched are copied as they were, and the margin shows what changed.
"""

from collections.abc import Iterable

from pydantic import ValidationError

from agents.da_understand_checks import describe_validation_error, is_vague_then
from pydantic_classes.da_refine_models import (
    REASON_LIMIT,
    CriterionChange,
    CriterionOp,
    FieldChange,
    LaneSuggestion,
    RecordDiff,
    RevisionReply,
)
from pydantic_classes.da_request_record_models import (
    CRITERION_PARTS,
    INTERPRETER_FIELDS,
    LIST_FIELDS,
    LIST_LENGTH_LIMIT,
    TEXT_FIELDS,
    AcceptanceCriterion,
    RequestRecord,
)

NO_CRITERION_REASON = "No criterion covers this, so it is a missing requirement."
CAP_TEXT = "This request has been refined {count} times. Get help, or hand off what you have."


# --- criteria: numbering that never reuses an ID ---


def criterion_number(criterion_id: str) -> int:
    """AC-6 gives 6."""
    return int(criterion_id.split("-")[1])


def next_criterion_number(records: Iterable[RequestRecord]) -> int:
    """One more than the highest ID in ANY version of this record, so a removed ID is never given
    out again (spec section 5, step 3)."""
    highest = 0
    for record in records:
        for criterion in record.acceptance_criteria:
            highest = max(highest, criterion_number(criterion.id))
    return highest + 1


def _text_of(criterion: AcceptanceCriterion) -> dict[str, str]:
    return {
        "kind": criterion.kind,
        **{part: getattr(criterion, part) for part in CRITERION_PARTS},
    }


def _same_text(left: AcceptanceCriterion, right: AcceptanceCriterion) -> bool:
    return _text_of(left) == _text_of(right)


def _duplicate_key(criterion: AcceptanceCriterion) -> tuple[str, str, str]:
    return tuple(  # type: ignore[return-value]
        " ".join(getattr(criterion, part).lower().split()) for part in CRITERION_PARTS
    )


# --- revision mode: apply the changes (D-C) ---


def apply_revision(
    record: RequestRecord, reply: RevisionReply, all_versions: list[RequestRecord]
) -> tuple[RequestRecord | None, list[str]]:
    """Apply the AI's operations to a COPY of `record`. Returns (new record, no problems) or
    (None, plain problems). Criteria the reply does not name are copied untouched; the version
    number goes up by one. `all_versions` holds every saved version, for the numbering."""
    problems = _field_update_problems(reply.field_updates)
    criteria = list(record.acceptance_criteria)
    number = next_criterion_number([*all_versions, record])
    for op in reply.criteria_ops:
        problem = _apply_op(criteria, op, number)
        if problem:
            problems.append(problem)
        elif op.op == "add":
            number += 1
    problems += _criteria_problems(criteria, record.acceptance_criteria)
    if problems:
        return None, problems
    data = record.model_dump()
    data.update(reply.field_updates)
    data["acceptance_criteria"] = [item.model_dump() for item in criteria]
    data["version"] = record.version + 1
    try:
        return RequestRecord.model_validate(data), []
    except ValidationError as error:
        return None, describe_validation_error(error)


def _field_update_problems(updates: dict) -> list[str]:
    problems = []
    for name, value in updates.items():
        if name not in INTERPRETER_FIELDS:
            problems.append(f"'{name}' is not a field that can change here.")
        elif name in TEXT_FIELDS and not isinstance(value, str):
            problems.append(f"'{name}' must be text, not a list.")
        elif name in LIST_FIELDS and not isinstance(value, list):
            problems.append(f"'{name}' must be a list of short items, not text.")
    return problems


def _apply_op(criteria: list[AcceptanceCriterion], op: CriterionOp, number: int) -> str:
    """Change `criteria` in place for one operation. Returns a problem text, or "" when fine."""
    if op.op == "add":
        if not (op.kind and op.given and op.when and op.then):
            return "A new criterion needs a kind, given, when and then."
        try:
            criteria.append(
                AcceptanceCriterion(
                    id=f"AC-{number}", kind=op.kind, given=op.given, when=op.when, then=op.then
                )
            )
        except ValidationError as error:
            return "; ".join(describe_validation_error(error))
        return ""
    index = next((i for i, item in enumerate(criteria) if item.id == op.id), None)
    if index is None:
        return f"{op.id or 'A criterion'} does not exist in this record, so it cannot change."
    if op.op == "remove":
        del criteria[index]
        return ""
    changes = {name: getattr(op, name) for name in ("kind", *CRITERION_PARTS) if getattr(op, name)}
    if not changes:
        return f"{op.id}: the change names no part to change."
    try:
        criteria[index] = AcceptanceCriterion(**(criteria[index].model_dump() | changes))
    except ValidationError as error:
        return f"{op.id}: " + "; ".join(describe_validation_error(error))
    return ""


def _criteria_problems(
    criteria: list[AcceptanceCriterion], original: list[AcceptanceCriterion]
) -> list[str]:
    """The Phase 2D checks: at most 12, an observable 'then', no repeats. Criteria the revision
    did not add or change were checked when they were confirmed and are not judged again."""
    before = {item.id: item for item in original}
    touched = {item.id for item in criteria if before.get(item.id) != item}
    problems = []
    if len(criteria) > LIST_LENGTH_LIMIT:
        problems.append(
            f"There would be {len(criteria)} acceptance criteria. The limit is {LIST_LENGTH_LIMIT}."
        )
    seen: dict[tuple[str, str, str], str] = {}
    for item in criteria:
        if item.id in touched and is_vague_then(item.then):
            problems.append(
                f"{item.id}: the 'then' part must say something a person or a test can see."
            )
        key = _duplicate_key(item)
        if key in seen:
            if item.id in touched or seen[key] in touched:
                problems.append(f"{item.id} repeats {seen[key]}: same given, when and then.")
        else:
            seen[key] = item.id
    return problems


# --- the diff of two versions (Summary tab) ---


def diff_records(old: RequestRecord, new: RequestRecord) -> RecordDiff:
    """Fields changed (old and new), criteria added, changed and removed."""
    fields = [
        FieldChange(field=name, old=getattr(old, name), new=getattr(new, name))
        for name in INTERPRETER_FIELDS
        if getattr(old, name) != getattr(new, name)
    ]
    before = {item.id: item for item in old.acceptance_criteria}
    after = {item.id: item for item in new.acceptance_criteria}
    criteria: list[CriterionChange] = []
    for criterion_id, item in after.items():
        if criterion_id not in before:
            criteria.append(CriterionChange(id=criterion_id, change="added", new=_text_of(item)))
        elif not _same_text(before[criterion_id], item):
            criteria.append(
                CriterionChange(
                    id=criterion_id,
                    change="changed",
                    old=_text_of(before[criterion_id]),
                    new=_text_of(item),
                )
            )
    for criterion_id, item in before.items():
        if criterion_id not in after:
            criteria.append(CriterionChange(id=criterion_id, change="removed", old=_text_of(item)))
    return RecordDiff(
        from_version=old.version, to_version=new.version, fields=fields, criteria=criteria
    )


def criterion_marks(diffs: list[RecordDiff]) -> dict[str, list[str]]:
    """criterion id -> ["added in v2", "changed in v3"...], for the version history."""
    marks: dict[str, list[str]] = {}
    for diff in diffs:
        for item in diff.criteria:
            marks.setdefault(item.id, []).append(f"{item.change} in v{diff.to_version}")
    return marks


# --- the lane suggestion (spec section 4) ---


def check_lane_suggestion(
    suggestion: LaneSuggestion, record: RequestRecord
) -> tuple[LaneSuggestion | None, str]:
    """Plain-code checks on the AI's lane reply. Returns (suggestion, "") or (None, why unusable).
    A bug with no criterion becomes a requirement suggestion (the demo's /*38*/ case)."""
    reason = suggestion.reason.strip()
    if not reason:
        return None, "The reason is empty."
    if len(reason) > REASON_LIMIT:
        return None, "The reason is too long."
    known = {item.id for item in record.acceptance_criteria}
    if suggestion.lane == "bug":
        if suggestion.criterion_id is None:
            return LaneSuggestion(lane="requirement", reason=NO_CRITERION_REASON), ""
        if suggestion.criterion_id not in known:
            return None, f"{suggestion.criterion_id} is not a criterion of this request."
    return suggestion.model_copy(update={"reason": reason}), ""


def refine_cap_reached(count: int, limit: int) -> bool:
    """The Refine cap (D-E): `limit` Refines per request, all lanes together."""
    return count >= limit


def cap_message(count: int) -> str:
    return CAP_TEXT.format(count=count)
