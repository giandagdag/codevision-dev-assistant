"""Made-up Approach data shared by the Approach tests. Nothing here calls an AI."""

from pydantic_classes.da_discovery_models import DiscoveryResult, Finding, SearchHit
from pydantic_classes.da_request_record_models import AcceptanceCriterion, RequestRecord

REQUEST_ID = "CVDA-2026-0001"
FILE_PATH_ONE = "src/agents/excel_processor.py"
FILE_PATH_TWO = "src/agents/upload_validator.py"


def sample_record(request_id=REQUEST_ID, criteria=3) -> RequestRecord:
    made = [
        AcceptanceCriterion(
            id=f"AC-{number}",
            kind="failure" if number == criteria else "success",
            given="a workbook",
            when="it is uploaded",
            then="something visible happens",
        )
        for number in range(1, criteria + 1)
    ]
    return RequestRecord(
        request_id=request_id,
        rulebook_version=1,
        title="Add Excel upload",
        objective="Let users upload Excel files",
        reason="Teams keep inventories in Excel",
        current_behaviour="Only PDF and DOCX are accepted",
        expected_behaviour="Excel files are processed",
        acceptance_criteria=made,
    )


def sample_discovery(request_id=REQUEST_ID) -> DiscoveryResult:
    def hit(number, path, symbol):
        return SearchHit(
            hit_id=number, source_path=path, symbol=symbol, kind="code", score=0.5, mode="exact",
            snippet="class Example:\n    pass", line_start=10,
        )

    return DiscoveryResult(
        request_id=request_id, round=1, record_version=1, rulebook_version=1,
        search_provider="fake", queries=["exact: x"],
        hits=[
            hit(1, "app/ingestion/pdf_processor.py", "PdfProcessor.extract_text"),
            hit(2, "app/ingestion/docx_processor.py", "DocxProcessor.extract_text"),
        ],
        findings=[
            Finding(kind="existing_capability", title="PDF extraction exists",
                    explanation="The PDF processor extracts text.", hit_ids=[1],
                    confidence="high"),
            Finding(kind="similar_implementation", title="Word uses the same flow",
                    explanation="Same pattern.", hit_ids=[2], confidence="medium"),
        ],
        limitations=[], summary_source="ai",
    )


def good_plan(**changes) -> dict:
    """A valid Generator reply for sample_discovery, as a dict."""
    values = {
        "summary": "Add Excel to the existing upload screen",
        "files": [
            {"path": FILE_PATH_ONE, "action": "create", "purpose": "Read sheets", "reuses": [1]},
            {"path": FILE_PATH_TWO, "action": "modify", "purpose": "Allow Excel", "reuses": []},
        ],
        "needs_people": [],
        "reuse_decisions": [
            {"hit_id": 1, "decision": "extend", "reason": "Same pattern"},
            {"hit_id": 2, "decision": "ignore", "reason": "PDF is closer"},
        ],
        "design_choices": [],
        "libraries": ["openpyxl"],
    }
    values.update(changes)
    return values


def design_choice(
    question="Where does Excel upload live?", options=("Existing screen", "New screen")
):
    return {
        "question": question,
        "impact": "Changes which screen is edited",
        "options": list(options),
    }


def good_test_plan(criteria=3) -> dict:
    return {
        "cases": [
            {"criterion_id": f"AC-{n}", "given": f"a workbook for case {n}",
             "expect": "the result is visible on the screen"}
            for n in range(1, criteria + 1)
        ]
    }
