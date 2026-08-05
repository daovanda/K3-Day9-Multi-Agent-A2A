from __future__ import annotations

from decimal import Decimal

from src.repository import DataRepository, money, money_float
from src.schemas import CaseInput, CaseOutput
from src.trace_logger import TraceLogger


class VerifierAgent:
    name = "verifier_agent"

    def __init__(self, repository: DataRepository, logger: TraceLogger):
        self.repository = repository
        self.logger = logger

    def run(self, case: CaseInput, output: CaseOutput) -> None:
        self.logger.event("agent_started", actor=self.name, case_id=case.case_id)
        errors: list[str] = []
        order_id = case.customer_request.claimed_order_id
        items = self.repository.get_items(order_id)
        payments = self.repository.get_payments(order_id)

        if output.case_id != case.case_id:
            errors.append("output case_id does not match input")
        if output.affected_entities.order_ids != [order_id]:
            errors.append("affected order_ids do not match the claimed order")

        expected_items = [f"{order_id}:{item.order_item_id}" for item in items]
        expected_sellers = sorted({item.seller_id for item in items})
        expected_payments = [
            f"{order_id}:{payment.payment_sequential}" for payment in payments
        ]
        if output.affected_entities.item_ids != expected_items:
            errors.append("affected item_ids do not match CSV rows")
        if output.affected_entities.seller_ids != expected_sellers:
            errors.append("affected seller_ids do not match CSV rows")
        if output.affected_entities.payment_ids != expected_payments:
            errors.append("affected payment_ids do not match CSV rows")

        expected_item_total = money(
            sum((Decimal(str(item.price_brl)) for item in items), Decimal("0"))
        )
        expected_freight = money(
            sum((Decimal(str(item.freight_brl)) for item in items), Decimal("0"))
        )
        expected_payment = money(
            sum((Decimal(str(row.payment_value_brl)) for row in payments), Decimal("0"))
        )
        financial = output.financial_resolution
        if financial.item_total_brl != money_float(expected_item_total):
            errors.append("item_total_brl does not match CSV")
        if financial.freight_total_brl != money_float(expected_freight):
            errors.append("freight_total_brl does not match CSV")
        if financial.payment_total_brl != money_float(expected_payment):
            errors.append("payment_total_brl does not match CSV")

        issue = output.assessment.primary_issue
        expected_refund = (
            money_float(expected_payment)
            if issue in {"canceled_order_paid", "unavailable_order_paid"}
            else money_float(expected_freight)
            if issue in {"late_delivery_seller", "late_delivery_logistics"}
            else 0.0
        )
        if financial.recommended_refund_brl != expected_refund:
            errors.append("recommended_refund_brl violates policy")
        expected_status = "action_required" if expected_refund > 0 else "no_action"
        if output.assessment.case_status != expected_status:
            errors.append("case_status is inconsistent with refund")

        if not output.evidence_ids:
            errors.append("evidence_ids is empty")
        for evidence_id in output.evidence_ids:
            if not self.repository.evidence_exists(evidence_id):
                errors.append(f"invalid evidence ID: {evidence_id}")

        cause = output.root_cause_analysis.ranked_causes[0].cause_code
        if f"policy:{cause}" not in output.evidence_ids:
            errors.append("root-cause policy evidence is missing")
        if output.resolution_actions == []:
            errors.append("resolution_actions is empty")

        if errors:
            self.logger.event(
                "verification_failed",
                actor=self.name,
                target="coordinator",
                case_id=case.case_id,
                details={"errors": errors},
            )
            raise ValueError(f"Verification failed for {case.case_id}: {'; '.join(errors)}")

        self.logger.event(
            "verification_passed",
            actor=self.name,
            target="coordinator",
            case_id=case.case_id,
            details={
                "checked_entities": (
                    1 + len(expected_items) + len(expected_sellers) + len(expected_payments)
                ),
                "checked_evidence": len(output.evidence_ids),
            },
        )

