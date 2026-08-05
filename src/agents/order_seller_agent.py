from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.llm_client import AgentLLM
from src.repository import DataRepository, money, money_float
from src.schemas import CaseInput, OrderSellerFinding
from src.trace_logger import TraceLogger


SYSTEM_PROMPT = """You are order_seller_agent in an e-commerce dispute team.
Audit only order status, order items, sellers, monetary item/freight totals, and
whether the carrier handoff timestamp is after each item's shipping limit.
Do not compare carrier_date with estimated_delivery_date; that comparison is
irrelevant. A missing carrier date for canceled/unavailable orders is normal.
Use only the supplied deterministic finding. Never invent IDs, timestamps, or
financial values. Return the AgentAudit schema with agent='order_seller_agent'
and the exact case_id supplied by the user."""


def _parse_timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class OrderSellerAgent:
    name = "order_seller_agent"

    def __init__(self, repository: DataRepository, logger: TraceLogger, llm: AgentLLM):
        self.repository = repository
        self.logger = logger
        self.llm = llm

    def run(self, case: CaseInput, *, use_llm: bool) -> OrderSellerFinding:
        order_id = case.customer_request.claimed_order_id
        self.logger.event("agent_started", actor=self.name, case_id=case.case_id)
        order = self.repository.get_order(order_id)
        items = self.repository.get_items(order_id)
        carrier_date = order["order_delivered_carrier_date"] or None
        carrier_dt = _parse_timestamp(carrier_date)
        late_sellers = sorted(
            {
                item.seller_id
                for item in items
                if carrier_dt is not None
                and carrier_dt > _parse_timestamp(item.shipping_limit_date)
            }
        )
        item_total = money(sum((Decimal(str(item.price_brl)) for item in items), Decimal("0")))
        freight_total = money(
            sum((Decimal(str(item.freight_brl)) for item in items), Decimal("0"))
        )
        finding = OrderSellerFinding(
            case_id=case.case_id,
            order_id=order_id,
            order_status=order["order_status"],
            carrier_date=carrier_date,
            customer_delivery_date=order["order_delivered_customer_date"] or None,
            estimated_delivery_date=order["order_estimated_delivery_date"] or None,
            item_ids=[f"{order_id}:{item.order_item_id}" for item in items],
            item_shipping_limits={
                f"{order_id}:{item.order_item_id}": item.shipping_limit_date
                for item in items
            },
            seller_ids=sorted({item.seller_id for item in items}),
            late_handoff_seller_ids=late_sellers,
            item_total_brl=money_float(item_total),
            freight_total_brl=money_float(freight_total),
        )
        if use_llm:
            self.llm.audit(
                agent_name=self.name,
                case_id=case.case_id,
                system_prompt=SYSTEM_PROMPT,
                finding=finding,
                source_context={"order": order, "items": items},
            )
        self.logger.event(
            "handoff",
            actor=self.name,
            target="coordinator",
            case_id=case.case_id,
            details={"finding": finding},
        )
        return finding
