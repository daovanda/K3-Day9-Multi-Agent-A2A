from __future__ import annotations

from src.llm_client import AgentLLM
from src.schemas import (
    CaseInput,
    DeliveryFinding,
    OrderSellerFinding,
    PaymentFinding,
    PolicyDecision,
    ResponsibleParty,
)
from src.trace_logger import TraceLogger


SYSTEM_PROMPT = """You are policy_agent applying EC_POLICY_V1.
Audit the already computed policy decision against this strict priority:
1 canceled paid; 2 unavailable paid; 3 late delivery with seller handoff after
limit; 4 late delivery with on-time seller handoff; 5 reconciled split payment;
6 on-time delivery with reconciled payment. Canceled/unavailable refund all
payments; late delivery refunds freight; other cases refund zero. Never replace
the deterministic decision. case_status='action_required' is correct whenever
refund is positive; case_status='no_action' is correct whenever refund is zero.
An unsupported late claim must be rejected when verified delivery is on time.
Return AgentAudit with agent='policy_agent' and the
exact supplied case_id."""


class PolicyAgent:
    name = "policy_agent"

    def __init__(self, logger: TraceLogger, llm: AgentLLM):
        self.logger = logger
        self.llm = llm

    def run(
        self,
        case: CaseInput,
        order: OrderSellerFinding,
        payment: PaymentFinding,
        delivery: DeliveryFinding,
        *,
        use_llm: bool,
    ) -> PolicyDecision:
        self.logger.event(
            "agent_started",
            actor=self.name,
            case_id=case.case_id,
            details={"received_findings": ["order_seller", "payment", "delivery"]},
        )
        if order.order_status == "canceled" and payment.payment_total_brl > 0:
            decision = PolicyDecision(
                primary_issue="canceled_order_paid",
                case_status="action_required",
                confidence=0.99,
                root_cause="ORDER_CANCELED_AFTER_PAYMENT",
                responsible_parties=[
                    ResponsibleParty(party_type="platform", party_id="OLIST_PLATFORM")
                ],
                recommended_refund_brl=payment.payment_total_brl,
                resolution_action="issue_full_refund",
            )
        elif order.order_status == "unavailable" and payment.payment_total_brl > 0:
            decision = PolicyDecision(
                primary_issue="unavailable_order_paid",
                case_status="action_required",
                confidence=0.99,
                root_cause="ORDER_UNAVAILABLE_AFTER_PAYMENT",
                responsible_parties=[
                    ResponsibleParty(party_type="platform", party_id="OLIST_PLATFORM")
                ],
                recommended_refund_brl=payment.payment_total_brl,
                resolution_action="issue_full_refund",
            )
        elif delivery.is_delivered_late and delivery.seller_handoff_late:
            decision = PolicyDecision(
                primary_issue="late_delivery_seller",
                case_status="action_required",
                confidence=0.99,
                root_cause="SELLER_HANDOFF_AFTER_LIMIT",
                responsible_parties=[
                    ResponsibleParty(party_type="seller", party_id=seller_id)
                    for seller_id in delivery.late_handoff_seller_ids
                ],
                recommended_refund_brl=order.freight_total_brl,
                resolution_action="refund_freight",
            )
        elif delivery.is_delivered_late:
            decision = PolicyDecision(
                primary_issue="late_delivery_logistics",
                case_status="action_required",
                confidence=0.99,
                root_cause="CARRIER_DELIVERED_AFTER_ESTIMATE",
                responsible_parties=[
                    ResponsibleParty(
                        party_type="logistics_provider", party_id="LOGISTICS_PROVIDER"
                    )
                ],
                recommended_refund_brl=order.freight_total_brl,
                resolution_action="refund_freight",
            )
        elif payment.payment_row_count >= 2 and payment.is_reconciled:
            decision = PolicyDecision(
                primary_issue="valid_split_payment",
                case_status="no_action",
                confidence=0.99,
                root_cause="MULTIPLE_PAYMENTS_RECONCILED",
                responsible_parties=[],
                recommended_refund_brl=0.0,
                resolution_action="explain_valid_split_payment",
            )
        elif not delivery.is_delivered_late and payment.is_reconciled:
            decision = PolicyDecision(
                primary_issue="unsupported_late_claim",
                case_status="no_action",
                confidence=0.99,
                root_cause="DELIVERY_WITHIN_ESTIMATE",
                responsible_parties=[],
                recommended_refund_brl=0.0,
                resolution_action="reject_late_refund",
            )
        else:
            raise ValueError(f"{case.case_id} does not match EC_POLICY_V1")

        if use_llm:
            self.llm.audit(
                agent_name=self.name,
                case_id=case.case_id,
                system_prompt=SYSTEM_PROMPT,
                finding=decision,
                source_context={
                    "order_seller_finding": order,
                    "payment_finding": payment,
                    "delivery_finding": delivery,
                },
            )
        self.logger.event(
            "handoff",
            actor=self.name,
            target="verifier_agent",
            case_id=case.case_id,
            details={"decision": decision},
        )
        return decision
