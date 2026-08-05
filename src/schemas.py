from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Issue = Literal[
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
]
RootCause = Literal[
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
]
Action = Literal[
    "issue_full_refund",
    "refund_freight",
    "explain_valid_split_payment",
    "reject_late_refund",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerRequest(StrictModel):
    language: str
    message: str
    claimed_order_id: str


class CaseInput(StrictModel):
    case_id: str
    opened_at: str
    customer_request: CustomerRequest
    policy_version: str


class ItemFact(StrictModel):
    order_item_id: int
    product_id: str
    seller_id: str
    shipping_limit_date: str
    price_brl: float
    freight_brl: float


class PaymentFact(StrictModel):
    payment_sequential: int
    payment_type: str
    payment_installments: int
    payment_value_brl: float


class OrderSellerFinding(StrictModel):
    case_id: str
    order_id: str
    order_status: str
    carrier_date: str | None
    customer_delivery_date: str | None
    estimated_delivery_date: str | None
    item_ids: list[str]
    item_shipping_limits: dict[str, str]
    seller_ids: list[str]
    late_handoff_seller_ids: list[str]
    item_total_brl: float
    freight_total_brl: float


class PaymentFinding(StrictModel):
    case_id: str
    order_id: str
    payment_ids: list[str]
    payment_row_count: int
    payment_total_brl: float
    expected_total_brl: float
    difference_brl: float
    is_reconciled: bool


class DeliveryFinding(StrictModel):
    case_id: str
    order_id: str
    is_delivered_late: bool
    seller_handoff_late: bool
    late_handoff_seller_ids: list[str]


class AgentAudit(StrictModel):
    case_id: str
    agent: Literal[
        "order_seller_agent",
        "payment_agent",
        "delivery_agent",
        "policy_agent",
    ]
    handoff_ready: Literal[True]
    schema_version: Literal["agent_audit_v1"]


class ResponsibleParty(StrictModel):
    party_type: Literal["seller", "logistics_provider", "platform"]
    party_id: str


class PolicyDecision(StrictModel):
    primary_issue: Issue
    case_status: Literal["action_required", "no_action"]
    confidence: float = Field(ge=0, le=1)
    root_cause: RootCause
    responsible_parties: list[ResponsibleParty]
    recommended_refund_brl: float
    resolution_action: Action


class Assessment(StrictModel):
    primary_issue: Issue
    case_status: Literal["action_required", "no_action"]
    confidence: float = Field(ge=0, le=1)


class AffectedEntities(StrictModel):
    order_ids: list[str] = Field(max_length=5)
    item_ids: list[str] = Field(max_length=5)
    seller_ids: list[str] = Field(max_length=5)
    payment_ids: list[str] = Field(max_length=5)


class RankedCause(StrictModel):
    cause_code: RootCause
    rank: int = Field(ge=1)


class RootCauseAnalysis(StrictModel):
    ranked_causes: list[RankedCause] = Field(max_length=3)
    responsible_parties: list[ResponsibleParty] = Field(max_length=3)


class FinancialResolution(StrictModel):
    currency: Literal["BRL"]
    item_total_brl: float
    freight_total_brl: float
    payment_total_brl: float
    recommended_refund_brl: float


class CaseOutput(StrictModel):
    case_id: str
    assessment: Assessment
    affected_entities: AffectedEntities
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(max_length=10)
    financial_resolution: FinancialResolution
    resolution_actions: list[Action] = Field(max_length=5)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value
