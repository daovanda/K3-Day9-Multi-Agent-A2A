from __future__ import annotations

from decimal import Decimal

from src.config import PAYMENT_TOLERANCE_BRL
from src.llm_client import AgentLLM
from src.repository import DataRepository, money, money_float
from src.schemas import CaseInput, OrderSellerFinding, PaymentFinding
from src.trace_logger import TraceLogger


SYSTEM_PROMPT = """You are payment_agent in an e-commerce dispute team.
Audit only payment reconciliation. payment_value is the value of each payment
row and must never be multiplied by payment_installments. A payment reconciles
when absolute difference from item_total + freight_total is <= 0.10 BRL.
Never invent payment rows or values. Return AgentAudit with
agent='payment_agent' and the exact supplied case_id."""


class PaymentAgent:
    name = "payment_agent"

    def __init__(self, repository: DataRepository, logger: TraceLogger, llm: AgentLLM):
        self.repository = repository
        self.logger = logger
        self.llm = llm

    def run(
        self,
        case: CaseInput,
        order_finding: OrderSellerFinding,
        *,
        use_llm: bool,
    ) -> PaymentFinding:
        order_id = case.customer_request.claimed_order_id
        self.logger.event(
            "agent_started",
            actor=self.name,
            case_id=case.case_id,
            details={"received_from": "coordinator"},
        )
        payments = self.repository.get_payments(order_id)
        payment_total = money(
            sum((Decimal(str(row.payment_value_brl)) for row in payments), Decimal("0"))
        )
        expected = money(
            Decimal(str(order_finding.item_total_brl))
            + Decimal(str(order_finding.freight_total_brl))
        )
        difference = money(payment_total - expected)
        finding = PaymentFinding(
            case_id=case.case_id,
            order_id=order_id,
            payment_ids=[f"{order_id}:{row.payment_sequential}" for row in payments],
            payment_row_count=len(payments),
            payment_total_brl=money_float(payment_total),
            expected_total_brl=money_float(expected),
            difference_brl=money_float(difference),
            is_reconciled=abs(difference) <= Decimal(PAYMENT_TOLERANCE_BRL),
        )
        if use_llm:
            self.llm.audit(
                agent_name=self.name,
                case_id=case.case_id,
                system_prompt=SYSTEM_PROMPT,
                finding=finding,
                source_context={
                    "payment_rows": payments,
                    "item_total_brl": order_finding.item_total_brl,
                    "freight_total_brl": order_finding.freight_total_brl,
                },
            )
        self.logger.event(
            "handoff",
            actor=self.name,
            target="coordinator",
            case_id=case.case_id,
            details={"finding": finding},
        )
        return finding
