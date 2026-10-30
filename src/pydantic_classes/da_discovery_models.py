"""Data shapes for Discover: search hits, findings and one saved search round.

The limits here (spec 3.1, 3.4) work like DDS field lengths: a value that is too long is refused,
never cut short.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from pydantic_classes.da_models import REQUEST_ID_PATTERN, Request
from pydantic_classes.da_request_record_models import ChatMessage, RequestRecord

SNIPPET_LIMIT = 500
FINDING_LIMIT = 8
TITLE_LIMIT = 80
EXPLANATION_LIMIT = 300
LIMITATION_LIMIT = 300
LIMITATION_COUNT_LIMIT = 4

HitKind = Literal["code", "doc", "standard", "config"]
SearchMode = Literal["exact", "meaning"]
FindingKind = Literal[
    "existing_capability", "similar_implementation", "relevant_standard", "affected_area"
]
Confidence = Literal["high", "medium", "low"]
SummarySource = Literal["ai", "fallback"]

# Findings of these kinds make the outcome SIMILAR_IMPLEMENTATION_FOUND (spec section 2).
MATCH_KINDS: tuple[str, ...] = ("existing_capability", "similar_implementation")
# These kinds must cite at least one hit (spec 3.4).
CITING_KINDS: tuple[str, ...] = (*MATCH_KINDS, "relevant_standard")

LimitationText = Annotated[str, Field(min_length=1, max_length=LIMITATION_LIMIT)]


class _Shape(BaseModel):
    # extra="forbid": an unknown field name is an error, not silently dropped.
    model_config = ConfigDict(extra="forbid")


class SearchFilters(_Shape):
    languages: list[str] = Field(default_factory=lambda: ["python"])
    include_deprecated: bool = False
    include_restricted: bool = False


class SearchHit(_Shape):
    # Set by the app (1, 2, 3...). 0 means "not numbered yet" (straight from an index).
    hit_id: int = Field(default=0, ge=0)
    source_path: str = Field(min_length=1)
    # Function or class name, such as UploadValidator.check_type. Empty for a whole file.
    symbol: str = ""
    line_start: int = Field(default=0, ge=0)
    # A commit ID when known, otherwise the index build ID. May be empty.
    version: str = ""
    kind: HitKind
    language: str = ""
    snippet: str = Field(default="", max_length=SNIPPET_LIMIT)
    score: float = Field(ge=0, le=1)
    mode: SearchMode


class Finding(_Shape):
    kind: FindingKind
    title: str = Field(min_length=1, max_length=TITLE_LIMIT)
    explanation: str = Field(min_length=1, max_length=EXPLANATION_LIMIT)
    hit_ids: list[int] = Field(default_factory=list)
    confidence: Confidence


class DiscoveryReply(_Shape):
    """The one AI reply: findings and limitations (spec 3.4)."""

    findings: list[Finding] = Field(default_factory=list, max_length=FINDING_LIMIT)
    limitations: list[LimitationText] = Field(
        default_factory=list, max_length=LIMITATION_COUNT_LIMIT
    )


class DiscoveryResult(_Shape):
    """One saved search round (a row in da_discovery_results)."""

    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    round: int = Field(ge=1)
    record_version: int = Field(ge=1)
    rulebook_version: int = Field(ge=1)
    search_provider: str
    queries: list[str]
    hits: list[SearchHit]
    findings: list[Finding]
    limitations: list[str]
    summary_source: SummarySource
    model: str = ""
    hint: str = ""
    created_at: AwareDatetime | None = None


class DiscoveryView(BaseModel):
    """Everything the screen needs to show Discover for one request."""

    request: Request
    record: RequestRecord
    messages: list[ChatMessage]
    status_label: str
    # The latest round, or None before the first one.
    result: DiscoveryResult | None
    outcome: str
    rounds_used: int
    max_rounds: int
    choices: list[str]
    can_hint: bool
    # Set after an escalation: "Escalated in Discover: ..." (spec 3.5).
    open_item: str
    revision: int
    demo_mode: bool
