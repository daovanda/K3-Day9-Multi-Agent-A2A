from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from src.config import OUTPUT_DIR, ROOT_DIR
from src.pipeline import EXPECTED_CASE_NAMES
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
        counts[issue] += 1

    return {"file_count": len(files), "issue_counts": dict(sorted(counts.items()))}


def validate_submission_zip(path: Path = ROOT_DIR / "submission.zip") -> None:
    with ZipFile(path) as archive:
        names = archive.namelist()
    if len(names) != 50 or set(names) != EXPECTED_CASE_NAMES:
        raise ValueError("submission.zip must contain exactly EC_001.json through EC_050.json")
    if any("/" in name or "\\" in name for name in names):
        raise ValueError("JSON files must be at the ZIP root")

