"""Data shapes for Discover: search hits, findings and one saved search round.

The limits here (spec 3.1, 3.4) work like DDS field lengths: a value that is too long is refused,
never cut short.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from pydantic_classes.da_enhance_models import ImpactResult
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
    # Fix 11-1: only these file paths (a capability's modules). Empty = the whole index.
    modules: list[str] = Field(default_factory=list)


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
    # The index reports these so our own safety filter can drop such hits (spec 3.1, rule R3).
    deprecated: bool = False
    restricted: bool = False
    # Fix 11-1: the capability this file belongs to, when Discover narrowed the search to one.
    capability: str = ""
    # Upgrade G3: modules that use this hit's module, from the code link graph (empty: no graph).
    used_by: list[str] = Field(default_factory=list)


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
    # Phase 9: what the impact walk found in this round (enhance requests only).
    impact: ImpactResult | None = None
    index_build: int | None = Field(default=None, ge=1)  # G5e: None = not recorded
    created_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _findings_cite_only_saved_hits(self) -> DiscoveryResult:
        saved = {hit.hit_id for hit in self.hits}
        for finding in self.findings:
            if not set(finding.hit_ids) <= saved:
                raise ValueError("A finding cites a hit number that is not in this round's hits.")
        return self


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
    # Why "Something's missing" is no longer offered (round cap reached), or empty.
    cap_message: str
    # Set after an escalation: "Escalated in Discover: ..." (spec 3.5).
    open_item: str
    revision: int
    demo_mode: bool
