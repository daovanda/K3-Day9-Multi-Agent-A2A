from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from src.config import LOGGING_DIR, MODEL_NAME, OUTPUT_DIR, ROOT_DIR
from src.pipeline import EXPECTED_CASE_NAMES, EXPECTED_ZIP_NAMES
from src.repository import DataRepository, money, money_float
from src.schemas import CaseOutput


ISSUE_CONTRACT: dict[str, tuple[str, str, str]] = {
    "canceled_order_paid": (
        "ORDER_CANCELED_AFTER_PAYMENT",
        "issue_full_refund",
        "action_required",
    ),
    "unavailable_order_paid": (
        "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        "issue_full_refund",
        "action_required",
    ),
    "late_delivery_seller": (
        "SELLER_HANDOFF_AFTER_LIMIT",
        "refund_freight",
        "action_required",
    ),
    "late_delivery_logistics": (
        "CARRIER_DELIVERED_AFTER_ESTIMATE",
        "refund_freight",
        "action_required",
    ),
    "valid_split_payment": (
        "MULTIPLE_PAYMENTS_RECONCILED",
        "explain_valid_split_payment",
        "no_action",
    ),
    "unsupported_late_claim": (
        "DELIVERY_WITHIN_ESTIMATE",
        "reject_late_refund",
        "no_action",
    ),
}


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def derive_expected_issue(repository: DataRepository, order_id: str) -> str:
    order = repository.get_order(order_id)
    items = repository.get_items(order_id)
    payments = repository.get_payments(order_id)
    payment_total = money(
        sum((Decimal(str(row.payment_value_brl)) for row in payments), Decimal("0"))
    )
    item_total = money(
        sum((Decimal(str(row.price_brl)) for row in items), Decimal("0"))
    )
    freight_total = money(
        sum((Decimal(str(row.freight_brl)) for row in items), Decimal("0"))
    )
    reconciled = abs(payment_total - item_total - freight_total) <= Decimal("0.10")
    delivered = _dt(order["order_delivered_customer_date"] or None)
    estimated = _dt(order["order_estimated_delivery_date"] or None)
    carrier = _dt(order["order_delivered_carrier_date"] or None)
    late = delivered is not None and estimated is not None and delivered > estimated
    seller_late = carrier is not None and any(
        carrier > _dt(item.shipping_limit_date) for item in items
    )
    if order["order_status"] == "canceled" and payment_total > 0:
        return "canceled_order_paid"
    if order["order_status"] == "unavailable" and payment_total > 0:
        return "unavailable_order_paid"
    if late and seller_late:
        return "late_delivery_seller"
    if late:
        return "late_delivery_logistics"
    if len(payments) >= 2 and reconciled:
        return "valid_split_payment"
    if not late and reconciled:
        return "unsupported_late_claim"
    raise ValueError(f"Order {order_id} does not match EC_POLICY_V1")


def validate_output_set(
    output_dir: Path = OUTPUT_DIR,
    repository: DataRepository | None = None,
) -> dict[str, Any]:
    repository = repository or DataRepository()
    cases = repository.load_cases()
    case_by_id = {case.case_id: case for case in cases}
    files = sorted(output_dir.glob("EC_*.json"))
    names = {path.name for path in files}
    if names != EXPECTED_CASE_NAMES:
        raise ValueError(
            f"Output filenames mismatch: missing={sorted(EXPECTED_CASE_NAMES - names)}, "
            f"extra={sorted(names - EXPECTED_CASE_NAMES)}"
        )

    counts: Counter = Counter()
    for path in files:
        with path.open("r", encoding="utf-8") as handle:
            output = CaseOutput.model_validate(json.load(handle))
        if output.case_id != path.stem:
            raise ValueError(f"Filename/case_id mismatch: {path.name}")
        case = case_by_id[output.case_id]
        order_id = case.customer_request.claimed_order_id
        expected_issue = derive_expected_issue(repository, order_id)
        issue = output.assessment.primary_issue
        if issue != expected_issue:
            raise ValueError(f"{output.case_id}: expected {expected_issue}, found {issue}")
        cause, action, status = ISSUE_CONTRACT[issue]
        if output.root_cause_analysis.ranked_causes[0].cause_code != cause:
            raise ValueError(f"{output.case_id}: incorrect root cause")
        if output.resolution_actions != [action]:
            raise ValueError(f"{output.case_id}: incorrect action")
        if output.assessment.case_status != status:
            raise ValueError(f"{output.case_id}: incorrect case status")

        items = repository.get_items(order_id)
        payments = repository.get_payments(order_id)
        expected_item_ids = [f"{order_id}:{row.order_item_id}" for row in items][:5]
        expected_seller_ids = sorted({row.seller_id for row in items})[:5]
        expected_payment_ids = [
            f"{order_id}:{row.payment_sequential}" for row in payments
        ][:5]
        affected = output.affected_entities
        if affected.order_ids != [order_id]:
            raise ValueError(f"{output.case_id}: incorrect affected order IDs")
        if affected.item_ids != expected_item_ids:
            raise ValueError(f"{output.case_id}: incorrect affected item IDs")
        if affected.seller_ids != expected_seller_ids:
            raise ValueError(f"{output.case_id}: incorrect affected seller IDs")
        if affected.payment_ids != expected_payment_ids:
            raise ValueError(f"{output.case_id}: incorrect affected payment IDs")

        order = repository.get_order(order_id)
        carrier = _dt(order["order_delivered_carrier_date"] or None)
        late_sellers = sorted(
            {
                row.seller_id
                for row in items
                if carrier is not None and carrier > _dt(row.shipping_limit_date)
            }
        )
        parties = [party.model_dump() for party in output.root_cause_analysis.responsible_parties]
        if issue in {"canceled_order_paid", "unavailable_order_paid"}:
            expected_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]
        elif issue == "late_delivery_logistics":
            expected_parties = [
                {
                    "party_type": "logistics_provider",
                    "party_id": "LOGISTICS_PROVIDER",
                }
            ]
        elif issue == "late_delivery_seller":
            expected_parties = [
                {"party_type": "seller", "party_id": seller_id}
                for seller_id in late_sellers
            ]
        else:
            expected_parties = []
        if parties != expected_parties:
            raise ValueError(f"{output.case_id}: incorrect responsible parties")

        item_total = money(
            sum((Decimal(str(row.price_brl)) for row in items), Decimal("0"))
        )
        freight_total = money(
            sum((Decimal(str(row.freight_brl)) for row in items), Decimal("0"))
        )
        payment_total = money(
            sum((Decimal(str(row.payment_value_brl)) for row in payments), Decimal("0"))
        )
        financial = output.financial_resolution
        expected_financial = (
            money_float(item_total),
            money_float(freight_total),
            money_float(payment_total),
        )
        actual_financial = (
            financial.item_total_brl,
            financial.freight_total_brl,
            financial.payment_total_brl,
        )
        if actual_financial != expected_financial:
            raise ValueError(f"{output.case_id}: financial totals do not match CSV")
        expected_refund = (
            money_float(payment_total)
            if issue in {"canceled_order_paid", "unavailable_order_paid"}
            else money_float(freight_total)
            if issue in {"late_delivery_seller", "late_delivery_logistics"}
            else 0.0
        )
        if financial.recommended_refund_brl != expected_refund:
            raise ValueError(f"{output.case_id}: incorrect refund")
        for evidence_id in output.evidence_ids:
            if not repository.evidence_exists(evidence_id):
                raise ValueError(f"{output.case_id}: invalid evidence {evidence_id}")
        if f"policy:{cause}" not in output.evidence_ids:
            raise ValueError(f"{output.case_id}: missing policy evidence")
        expected_evidence = [f"order:{order_id}"]
        if issue in {
            "late_delivery_seller",
            "late_delivery_logistics",
            "valid_split_payment",
            "unsupported_late_claim",
        }:
            expected_evidence.extend(f"item:{item_id}" for item_id in expected_item_ids)
        if issue in {
            "canceled_order_paid",
            "unavailable_order_paid",
            "valid_split_payment",
            "unsupported_late_claim",
        }:
            expected_evidence.extend(
                f"payment:{payment_id}" for payment_id in expected_payment_ids
            )
        if issue == "late_delivery_seller":
            expected_evidence.extend(f"seller:{seller_id}" for seller_id in late_sellers)
        expected_evidence = expected_evidence[:9] + [f"policy:{cause}"]
        if output.evidence_ids != expected_evidence:
            raise ValueError(f"{output.case_id}: evidence set/order is not canonical")
        counts[issue] += 1

    return {"file_count": len(files), "issue_counts": dict(sorted(counts.items()))}


def validate_trace(log_dir: Path = LOGGING_DIR) -> dict[str, Any]:
    trace_path = log_dir / "trace.jsonl"
    metadata_path = log_dir / "metadata.json"
    if not trace_path.is_file() or not metadata_path.is_file():
        raise ValueError("trace.jsonl and metadata.json are required")
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("trace.jsonl is empty")
    records = [json.loads(line) for line in lines]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_sequence = list(range(1, len(records) + 1))
    if [record.get("sequence") for record in records] != expected_sequence:
        raise ValueError("trace sequence is not contiguous")
    run_ids = {record.get("run_id") for record in records}
    if run_ids != {metadata.get("run_id")}:
        raise ValueError("trace and metadata run_id mismatch")
    if records[0].get("event_type") != "run_started":
        raise ValueError("first trace event must be run_started")
    if records[-1].get("event_type") != "run_completed":
        raise ValueError("last trace event must be run_completed")
    if metadata.get("status") != "completed" or metadata.get("processed_cases") != 50:
        raise ValueError("metadata does not describe a successful 50-case run")
    if metadata.get("model") != MODEL_NAME:
        raise ValueError("metadata model does not match source configuration")
    if metadata.get("model_approval") != "approved by instructor for this lab":
        raise ValueError("metadata does not record instructor model approval")
    if metadata.get("trace_events") != len(records):
        raise ValueError("metadata trace event count mismatch")

    failure_events = [
        record
        for record in records
        if record.get("event_type")
        in {"llm_call_failed", "verification_failed", "run_failed", "case_failed"}
    ]
    if failure_events:
        raise ValueError(f"official trace contains {len(failure_events)} failure events")
    by_type = Counter(record.get("event_type") for record in records)
    required_counts = {
        "case_started": 50,
        "case_completed": 50,
        "task_assigned": 200,
        "agent_started": 250,
        "handoff": 200,
        "verification_passed": 50,
        "output_written": 50,
    }
    for event_type, expected in required_counts.items():
        if by_type[event_type] != expected:
            raise ValueError(
                f"trace event {event_type}: expected {expected}, found {by_type[event_type]}"
            )

    llm_mode = metadata.get("llm_mode")
    expected_llm_calls = {"off": 0, "policy": 50, "all": 200}.get(llm_mode)
    if expected_llm_calls is None:
        raise ValueError(f"invalid metadata llm_mode: {llm_mode}")
    if by_type["llm_call_started"] != expected_llm_calls:
        raise ValueError("llm_call_started count does not match llm_mode")
    if by_type["llm_call_completed"] != expected_llm_calls:
        raise ValueError("llm_call_completed count does not match llm_mode")
    completed_calls = [
        record for record in records if record.get("event_type") == "llm_call_completed"
    ]
    for record in completed_calls:
        details = record.get("details", {})
        audit = details.get("audit", {})
        if details.get("requested_model") != MODEL_NAME:
            raise ValueError("trace contains an unexpected requested model")
        if not str(details.get("response_model", "")).startswith(MODEL_NAME):
            raise ValueError("trace contains an unexpected response model")
        if audit.get("handoff_ready") is not True:
            raise ValueError("LLM handoff acknowledgement is incomplete")
        if audit.get("case_id") != record.get("case_id"):
            raise ValueError("LLM audit case identity mismatch")

    raw_trace = trace_path.read_text(encoding="utf-8")
    if re.search(r"sk-(?:proj-)?[A-Za-z0-9_-]{8,}", raw_trace):
        raise ValueError("possible OpenAI API key found in trace")
    return {
        "run_id": metadata["run_id"],
        "trace_events": len(records),
        "llm_mode": llm_mode,
        "llm_calls": expected_llm_calls,
        "failed_events": 0,
    }


def validate_repository_deliverables(root_dir: Path = ROOT_DIR) -> dict[str, Any]:
    architecture = root_dir / "architecture.md"
    report = root_dir / "individual_01089_DaoVanDa.md"
    required_files = [
        architecture,
        report,
        root_dir / "RUNBOOK.md",
        root_dir / "requirements.txt",
        root_dir / ".env.example",
    ]
    missing = [path.name for path in required_files if not path.is_file()]
    if missing:
        raise ValueError(f"missing repository deliverables: {missing}")
    if architecture.stat().st_size < 1000:
        raise ValueError("architecture.md is unexpectedly incomplete")
    report_text = report.read_text(encoding="utf-8")
    if "Đào Văn Đà" not in report_text or "01089" not in report_text:
        raise ValueError("personal report identity is incomplete")
    if "[CẦN ĐIỀN]" in report_text:
        raise ValueError("personal report still contains required placeholders")
    if (root_dir / "individual_5SoCuoiMHV_HoVaTen.md").exists():
        raise ValueError("template report filename was not replaced")
    return {
        "architecture": architecture.name,
        "personal_report": report.name,
        "model": MODEL_NAME,
        "model_approval": "approved by instructor",
    }


def validate_submission_zip(path: Path = ROOT_DIR / "submission.zip") -> None:
    with ZipFile(path) as archive:
        names = archive.namelist()
    if len(names) != 50 or set(names) != EXPECTED_ZIP_NAMES:
        raise ValueError(
            "submission.zip must contain exactly output/EC_001.json through "
            "output/EC_050.json"
        )
