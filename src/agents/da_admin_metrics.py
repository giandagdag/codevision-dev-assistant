"""The health numbers on the Admin Overview (Phase 11c, spec section 12). Plain code, no AI.

The SQL is in db_table_functions/db_tbl_da_metrics.py; this file decides what a row means and how
a number is worded. A number with no rows says "No data yet", never a 0 dressed as a result.

What the words mean (fixed in specs/phase-11c-plan.md):
- Closed build: a build or rebuild run that has ended. Stopped, escalated and interrupted runs are
  closed builds too and count as "did not pass". "Check my edits" runs are left out.
- First-round pass: round 1 passed Layer A and Layer B, by the build loop's own test
  (layer A has no problems, and layer B ran, did not time out, had tests and none failed).
- Fix rounds: rounds used minus the first one.
- Get help: a request that moved to ESCALATION_REQUIRED, or has an escalation event (the Enhance
  screen writes only the event).
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from db_table_functions.da_db import open_db, to_db_time
from db_table_functions.db_tbl_da_audit import ensure_audit_table
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_metrics import (
    STATUS_EVENT,
    closed_build_rows,
    help_event_rows,
    highest_record_versions,
    kept_findings_by_check_and_severity,
    request_rows,
    review_counts,
    scanned_file_counts,
)
from db_table_functions.db_tbl_da_tester import count_kept_cites
from db_table_functions.db_tbl_da_workspace import ensure_workspace_tables
from pydantic_classes.da_build_models import LayerAResult, LayerBResult
from pydantic_classes.da_tester_models import CHECK_NAMES

WINDOW_30_DAYS = "30d"
WINDOW_ALL = "all"
WINDOW_LABELS = {WINDOW_30_DAYS: "Last 30 days", WINDOW_ALL: "All time"}
WINDOW_DAYS = 30

NO_DATA = "No data yet"
NO_DATA_PHASE_10 = "No data yet (comes with Phase 10)"
GET_HELP_LABEL = "Get help only; the other four triggers come with Phase 10"
ESCALATION_STATUS = "ESCALATION_REQUIRED"
REQUEST_KINDS = ("new", "enhance", "fix")
SEVERITY_ORDER = ("must_fix", "should_fix", "fyi")
RULES_CITED_SHOWN = 5


@dataclass(frozen=True)
class Metric:
    """One health number. value is None when there are no rows; text is what the screen shows."""

    label: str
    value: float | int | None
    text: str
    items: tuple[tuple[str, int], ...] = ()  # for the grouped numbers: (name, count)
    note: str = ""


@dataclass(frozen=True)
class HealthReport:
    window: str
    requests: Metric
    first_round_pass: Metric
    fix_rounds: Metric
    revisions: Metric
    files_edited: Metric
    escalations: Metric
    handoffs: Metric
    findings_by_check: Metric
    findings_by_severity: Metric
    unable_reviews: Metric
    rules_cited: Metric

    @property
    def all_metrics(self) -> list[Metric]:
        return [
            self.requests,
            self.first_round_pass,
            self.fix_rounds,
            self.revisions,
            self.files_edited,
            self.escalations,
            self.handoffs,
            self.findings_by_check,
            self.findings_by_severity,
            self.unable_reviews,
            self.rules_cited,
        ]


def window_start(window: str, now: datetime | None = None) -> str | None:
    """Database time text for the start of the window, or None for All time."""
    if window == WINDOW_ALL:
        return None
    moment = now or datetime.now(UTC)
    return to_db_time(moment - timedelta(days=WINDOW_DAYS))


def health_report(
    db_path: Path, window: str = WINDOW_ALL, now: datetime | None = None
) -> HealthReport:
    """Every health number for the window. Safe on a database with no build or Tester tables yet."""
    since = window_start(window, now)
    with open_db(db_path) as conn:
        ensure_build_tables(conn)  # also makes the Understand, Tester and Enhance tables
        ensure_audit_table(conn)
        ensure_workspace_tables(conn)
        requests = request_rows(conn, since)
        builds = closed_build_rows(conn, since)
        versions = highest_record_versions(conn, since)
        files, edited_requests = scanned_file_counts(conn, since)
        help_rows = help_event_rows(conn, since)
        findings = kept_findings_by_check_and_severity(conn, since)
        reviews, unable = review_counts(conn, since)
        cites = count_kept_cites(conn, since)
    request_total = len(requests)
    return HealthReport(
        window=window,
        requests=_requests_metric(requests),
        first_round_pass=_pass_rate(builds),
        fix_rounds=_fix_rounds(builds),
        revisions=_revisions(versions),
        files_edited=_files_edited(files, edited_requests, request_total),
        escalations=_escalations(help_rows, request_total),
        handoffs=Metric("Handoffs", None, NO_DATA_PHASE_10),
        findings_by_check=_findings_by_check(findings),
        findings_by_severity=_findings_by_severity(findings),
        unable_reviews=_unable(reviews, unable),
        rules_cited=_rules_cited(cites),
    )


def _no_data(label: str) -> Metric:
    return Metric(label, None, NO_DATA)


def _request_kind(enhance_state: str | None) -> str:
    # No Enhance row means a new-code request. The kind sits inside the state JSON.
    if not enhance_state:
        return "new"
    try:
        kind = json.loads(enhance_state).get("kind", "enhance")
    except (ValueError, AttributeError):
        return "enhance"
    return kind if kind in REQUEST_KINDS else "enhance"


def _requests_metric(rows) -> Metric:
    label = "Requests"
    if not rows:
        return _no_data(label)
    counts = dict.fromkeys(REQUEST_KINDS, 0)
    for row in rows:
        counts[_request_kind(row["enhance_state"])] += 1
    split = ", ".join(f"{kind} {counts[kind]}" for kind in REQUEST_KINDS)
    return Metric(label, len(rows), f"{len(rows)} ({split})", tuple(counts.items()))


def _round_one_passed(row) -> bool:
    # The same test the build loop uses: layer A ok and layer B present and ok.
    if row["layer_a"] is None or row["layer_b"] is None:
        return False
    try:
        layer_a = LayerAResult.model_validate_json(row["layer_a"])
        layer_b = LayerBResult.model_validate_json(row["layer_b"])
    except ValidationError:
        return False
    return layer_a.ok and layer_b.ok


def _pass_rate(builds) -> Metric:
    label = "First-round pass rate"
    if not builds:
        return _no_data(label)
    passed = sum(1 for row in builds if _round_one_passed(row))
    rate = 100 * passed / len(builds)
    return Metric(label, rate, f"{rate:.0f}% ({passed} of {len(builds)} closed builds)")


def _fix_rounds(builds) -> Metric:
    label = "Average fix rounds"
    if not builds:
        return _no_data(label)
    average = sum(max(row["rounds_used"] - 1, 0) for row in builds) / len(builds)
    return Metric(label, average, f"{average:.1f} per closed build")


def _revisions(versions: list[int]) -> Metric:
    label = "Requirement revisions per request"
    if not versions:
        return _no_data(label)
    average = sum(version - 1 for version in versions) / len(versions)
    return Metric(label, average, f"{average:.1f} per request")


def _files_edited(files: int, edited_requests: int, request_total: int) -> Metric:
    label = "Files edited by developers"
    if not request_total:
        return _no_data(label)
    share = 100 * edited_requests / request_total
    text = f"{files} files; {edited_requests} of {request_total} requests ({share:.0f}%)"
    return Metric(label, files, text)


def _is_get_help(row) -> bool:
    if row["event_type"] != STATUS_EVENT:
        return True  # escalated / discovery_escalated
    try:
        return json.loads(row["details"]).get("to") == ESCALATION_STATUS
    except (ValueError, AttributeError):
        return False


def _escalations(help_rows, request_total: int) -> Metric:
    label = "Escalations"
    if not request_total:
        return _no_data(label)
    count = len({row["request_id"] for row in help_rows if _is_get_help(row)})
    return Metric(label, count, str(count), note=GET_HELP_LABEL)


def _findings_by_check(rows) -> Metric:
    label = "Tester findings by check"
    if not rows:
        return _no_data(label)
    per_check: dict[int, int] = {}
    for row in rows:
        per_check[row["check_number"]] = per_check.get(row["check_number"], 0) + row["total"]
    items = tuple(
        (f"{number}. {CHECK_NAMES.get(number, 'Check ' + str(number))}", per_check[number])
        for number in sorted(per_check)
    )
    return Metric(label, sum(per_check.values()), f"{sum(per_check.values())} kept", items)


def _findings_by_severity(rows) -> Metric:
    label = "Tester findings by severity"
    if not rows:
        return _no_data(label)
    per_severity: dict[str, int] = {}
    for row in rows:
        per_severity[row["severity"]] = per_severity.get(row["severity"], 0) + row["total"]
    known = [name for name in SEVERITY_ORDER if name in per_severity]
    other = sorted(name for name in per_severity if name not in SEVERITY_ORDER)
    items = tuple((name, per_severity[name]) for name in [*known, *other])
    return Metric(label, sum(per_severity.values()), f"{sum(per_severity.values())} kept", items)


def _unable(reviews: int, unable: int) -> Metric:
    label = "Unable to assess"
    if not reviews:
        return _no_data(label)
    return Metric(label, unable, f"{unable} of {reviews} reviews")


def _rules_cited(cites: dict[str, int]) -> Metric:
    label = "Rules cited"
    if not cites:
        return _no_data(label)
    top = sorted(cites.items(), key=lambda item: (-item[1], item[0]))[:RULES_CITED_SHOWN]
    return Metric(label, sum(cites.values()), f"top {len(top)}", tuple(top))
