"""Data shapes for the Developer Assistant: a Request and its AuditEvents."""

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# CVDA-YYYY-NNNN. Four or more digits, so number 10000 still fits in a busy year.
REQUEST_ID_PATTERN = r"^CVDA-\d{4}-\d{4,}$"

STATUS_NEW = "NEW"

Actor = Literal["developer", "system", "llm"]


class Request(BaseModel):
    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    title: str = Field(min_length=1)
    developer_id: str = Field(min_length=1)
    status: str = STATUS_NEW
    version: int = Field(default=1, ge=1)
    # AwareDatetime refuses times without a time zone, so every stored time is clearly UTC.
    created_at: AwareDatetime
    updated_at: AwareDatetime
    # Empty until Phase 1 adds the rulebook.
    rulebook_version: str | None = None


class AuditEvent(BaseModel):
    # frozen=True: once built, an event cannot be changed in memory either (rule R1).
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    timestamp: AwareDatetime
    actor: Actor
    event_type: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
