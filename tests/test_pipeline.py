from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.config import LOGGING_DIR, OUTPUT_DIR
from src.pipeline import (
    EXPECTED_CASE_NAMES,
    EXPECTED_ZIP_NAMES,
    build_submission_zip,
    run_pipeline,
)
from src.repository import DataRepository
from src.schemas import CaseOutput
from src.validation import (
    validate_output_set,
    validate_repository_deliverables,
    validate_submission_zip,
    validate_trace,
)


EXPECTED_DISTRIBUTION = {
    "canceled_order_paid": 8,
    "late_delivery_logistics": 8,
    "late_delivery_seller": 8,
    "unavailable_order_paid": 8,
    "unsupported_late_claim": 9,
    "valid_split_payment": 9,
}


@pytest.fixture(scope="module")
def completed_run() -> Counter:
    # Preserve a valid official API trace/output when tests are run after the
    # submission pipeline. On a clean checkout, generate deterministic outputs.
    if {path.name for path in OUTPUT_DIR.glob("EC_*.json")} == EXPECTED_CASE_NAMES:
        result = validate_output_set()
        return Counter(result["issue_counts"])
    return run_pipeline(llm_mode="off")


def test_all_inputs_are_present_and_resolvable():
    repository = DataRepository()
    cases = repository.load_cases()
    assert len(cases) == 50
    assert len({case.case_id for case in cases}) == 50
    assert all(
        repository.get_order(case.customer_request.claimed_order_id) for case in cases
    )


def test_offline_pipeline_distribution(completed_run):
    assert dict(sorted(completed_run.items())) == EXPECTED_DISTRIBUTION


def test_all_outputs_pass_independent_validation(completed_run):
    result = validate_output_set()
    assert result["file_count"] == 50
    assert result["issue_counts"] == EXPECTED_DISTRIBUTION


def test_output_schema_and_limits(completed_run):
    assert {path.name for path in OUTPUT_DIR.glob("EC_*.json")} == EXPECTED_CASE_NAMES
    for path in OUTPUT_DIR.glob("EC_*.json"):
        output = CaseOutput.model_validate_json(path.read_text(encoding="utf-8"))
        assert len(output.affected_entities.order_ids) <= 5
        assert len(output.affected_entities.item_ids) <= 5
        assert len(output.affected_entities.seller_ids) <= 5
        assert len(output.affected_entities.payment_ids) <= 5
        assert len(output.evidence_ids) <= 10
        assert len(output.root_cause_analysis.ranked_causes) <= 3
        assert len(output.root_cause_analysis.responsible_parties) <= 3
        assert len(output.resolution_actions) <= 5


def test_logging_is_automatic_and_complete(completed_run):
    trace_path = LOGGING_DIR / "trace.jsonl"
    metadata_path = LOGGING_DIR / "metadata.json"
    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert records[0]["event_type"] == "run_started"
    assert records[-1]["event_type"] == "run_completed"
    assert metadata["status"] == "completed"
    assert metadata["processed_cases"] == 50
    assert metadata["model"] == "gpt-4o-mini"
    completed_cases = {
        row["case_id"] for row in records if row["event_type"] == "case_completed"
    }
    assert len(completed_cases) == 50
    raw_trace = trace_path.read_text(encoding="utf-8").lower()
    assert "sk-proj-" not in raw_trace
    assert "openai_api_key" not in raw_trace


def test_official_trace_contract(completed_run):
    result = validate_trace()
    assert result["trace_events"] > 0
    assert result["failed_events"] == 0


def test_repository_deliverables_are_complete(completed_run):
    result = validate_repository_deliverables()
    assert result["personal_report"] == "individual_01089_DaoVanDa.md"


def test_submission_zip_has_required_output_directory(completed_run):
    destination = OUTPUT_DIR.parent / "submission.test.zip"
    try:
        destination = build_submission_zip(destination=destination)
        validate_submission_zip(destination)
        with ZipFile(destination) as archive:
            assert set(archive.namelist()) == EXPECTED_ZIP_NAMES
    finally:
        destination.unlink(missing_ok=True)
