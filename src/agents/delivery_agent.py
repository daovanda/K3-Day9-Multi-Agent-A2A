from __future__ import annotations

from datetime import datetime

from src.llm_client import AgentLLM
from src.schemas import CaseInput, DeliveryFinding, OrderSellerFinding
from src.trace_logger import TraceLogger


SYSTEM_PROMPT = """You are delivery_agent in an e-commerce dispute team.
Audit delivery timing only. Delivery is late only when the actual customer
delivery timestamp is after the estimated delivery timestamp. Seller handoff is
late only when the carrier timestamp is after an item's shipping_limit_date.
Use timestamps exactly as supplied without timezone conversion. Return
AgentAudit with agent='delivery_agent' and the exact supplied case_id."""


def _parse_timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class DeliveryAgent:
    name = "delivery_agent"

    def __init__(self, logger: TraceLogger, llm: AgentLLM):
        self.logger = logger
        self.llm = llm

    def run(
        self,
        case: CaseInput,
        order_finding: OrderSellerFinding,
        *,
        use_llm: bool,
    ) -> DeliveryFinding:
        self.logger.event(
            "agent_started",
            actor=self.name,
            case_id=case.case_id,
            details={"received_from": "coordinator"},
        )
        delivered = _parse_timestamp(order_finding.customer_delivery_date)
        estimated = _parse_timestamp(order_finding.estimated_delivery_date)
        is_late = delivered is not None and estimated is not None and delivered > estimated
        finding = DeliveryFinding(
            case_id=case.case_id,
            order_id=order_finding.order_id,
            is_delivered_late=is_late,
            seller_handoff_late=bool(order_finding.late_handoff_seller_ids),
            late_handoff_seller_ids=order_finding.late_handoff_seller_ids,
        )
        if use_llm:
            self.llm.audit(
                agent_name=self.name,
                case_id=case.case_id,
                system_prompt=SYSTEM_PROMPT,
                finding=finding,
                source_context=order_finding,
            )
        self.logger.event(
            "handoff",
            actor=self.name,
            target="coordinator",
            case_id=case.case_id,
            details={"finding": finding},
        )
        return finding
