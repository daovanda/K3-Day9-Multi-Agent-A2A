from __future__ import annotations

import json
from pathlib import Path

from src.agents.delivery_agent import DeliveryAgent
from src.agents.order_seller_agent import OrderSellerAgent
from src.agents.payment_agent import PaymentAgent
from src.agents.policy_agent import PolicyAgent
from src.agents.verifier_agent import VerifierAgent
from src.llm_client import AgentLLM
from src.repository import DataRepository
from src.schemas import (
    AffectedEntities,
    Assessment,
    CaseInput,
    CaseOutput,
    FinancialResolution,
    RankedCause,
    RootCauseAnalysis,
)
from src.trace_logger import TraceLogger


class Coordinator:
    name = "coordinator"

    def __init__(
        self,
        repository: DataRepository,
        logger: TraceLogger,
        output_dir: Path,
        llm_mode: str,
    ):
        self.repository = repository
        self.logger = logger
        self.output_dir = output_dir
        self.llm_mode = llm_mode
        llm = AgentLLM(logger, enabled=llm_mode != "off")
        self.order_agent = OrderSellerAgent(repository, logger, llm)
        self.payment_agent = PaymentAgent(repository, logger, llm)
        self.delivery_agent = DeliveryAgent(logger, llm)
        self.policy_agent = PolicyAgent(logger, llm)
        self.verifier = VerifierAgent(repository, logger)

    def process(self, case: CaseInput) -> CaseOutput:
        self.logger.event(
            "case_started",
            actor=self.name,
            case_id=case.case_id,
            details={
                "order_id": case.customer_request.claimed_order_id,
                "policy_version": case.policy_version,
            },
        )
        if case.policy_version != "EC_POLICY_V1":
            raise ValueError(f"Unsupported policy version: {case.policy_version}")

        specialist_llm = self.llm_mode == "all"
        policy_llm = self.llm_mode in {"policy", "all"}
        self.logger.event(
            "task_assigned",
            actor=self.name,
            target="order_seller_agent",
            case_id=case.case_id,
        )
        order = self.order_agent.run(case, use_llm=specialist_llm)
        self.logger.event(
            "task_assigned",
            actor=self.name,
            target="payment_agent",
            case_id=case.case_id,
        )
        payment = self.payment_agent.run(case, order, use_llm=specialist_llm)
        self.logger.event(
            "task_assigned",
            actor=self.name,
            target="delivery_agent",
            case_id=case.case_id,
        )
        delivery = self.delivery_agent.run(case, order, use_llm=specialist_llm)
        self.logger.event(
            "task_assigned",
            actor=self.name,
            target="policy_agent",
            case_id=case.case_id,
        )
        decision = self.policy_agent.run(
            case,
            order,
            payment,
            delivery,
            use_llm=policy_llm,
        )

        evidence_ids = [f"order:{order.order_id}"]
        evidence_ids.extend(f"item:{item_id}" for item_id in order.item_ids)
        evidence_ids.extend(f"payment:{payment_id}" for payment_id in payment.payment_ids)
        if decision.primary_issue == "late_delivery_seller":
            evidence_ids.extend(
                f"seller:{party.party_id}"
                for party in decision.responsible_parties
                if party.party_type == "seller"
            )
        evidence_ids.append(f"policy:{decision.root_cause}")

        output = CaseOutput(
            case_id=case.case_id,
            assessment=Assessment(
                primary_issue=decision.primary_issue,
                case_status=decision.case_status,
                confidence=decision.confidence,
            ),
            affected_entities=AffectedEntities(
                order_ids=[order.order_id],
                item_ids=order.item_ids,
                seller_ids=order.seller_ids,
                payment_ids=payment.payment_ids,
            ),
            root_cause_analysis=RootCauseAnalysis(
                ranked_causes=[RankedCause(cause_code=decision.root_cause, rank=1)],
                responsible_parties=decision.responsible_parties,
            ),
            evidence_ids=evidence_ids,
            financial_resolution=FinancialResolution(
                currency="BRL",
                item_total_brl=order.item_total_brl,
                freight_total_brl=order.freight_total_brl,
                payment_total_brl=payment.payment_total_brl,
                recommended_refund_brl=decision.recommended_refund_brl,
            ),
            resolution_actions=[decision.resolution_action],
        )
        self.verifier.run(case, output)
        self._write_output(output)
        self.logger.event(
            "case_completed",
            actor=self.name,
            case_id=case.case_id,
            details={
                "primary_issue": output.assessment.primary_issue,
                "output_file": f"output/{case.case_id}.json",
            },
        )
        return output

    def _write_output(self, output: CaseOutput) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        destination = self.output_dir / f"{output.case_id}.json"
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(output.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
        self.logger.event(
            "output_written",
            actor=self.name,
            target="filesystem",
            case_id=output.case_id,
            details={"path": f"output/{destination.name}"},
        )

