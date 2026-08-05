from __future__ import annotations

import json

import pytest

from src.agents.delivery_agent import DeliveryAgent
from src.agents.policy_agent import PolicyAgent
from src.config import OUTPUT_DIR
from src.schemas import (
    CaseInput,
    CustomerRequest,
    DeliveryFinding,
    OrderSellerFinding,
    PaymentFinding,
)


class NoopDependency:
    def event(self, *args, **kwargs):
        return None

    def audit(self, *args, **kwargs):
        return None


def make_case() -> CaseInput:
    return CaseInput(
        case_id="EC_TEST",
        opened_at="2018-10-18T00:00:00-03:00",
        customer_request=CustomerRequest(
            language="vi",
            message="test",
            claimed_order_id="order-test",
        ),
        policy_version="EC_POLICY_V1",
    )


def make_order(**overrides) -> OrderSellerFinding:
    values = {
        "case_id": "EC_TEST",
        "order_id": "order-test",
        "order_status": "delivered",
        "carrier_date": "2018-01-02 08:00:00",
        "customer_delivery_date": "2018-01-05 08:00:00",
        "estimated_delivery_date": "2018-01-06 00:00:00",
        "item_ids": ["order-test:1"],
        "item_shipping_limits": {"order-test:1": "2018-01-03 00:00:00"},
        "seller_ids": ["seller-a"],
        "late_handoff_seller_ids": [],
        "item_total_brl": 100.0,
        "freight_total_brl": 10.0,
    }
    values.update(overrides)
    return OrderSellerFinding(**values)


def make_payment(**overrides) -> PaymentFinding:
    values = {
        "case_id": "EC_TEST",
        "order_id": "order-test",
        "payment_ids": ["order-test:1"],
        "payment_row_count": 1,
        "payment_total_brl": 110.0,
        "expected_total_brl": 110.0,
        "difference_brl": 0.0,
        "is_reconciled": True,
    }
    values.update(overrides)
    return PaymentFinding(**values)


def test_missing_delivery_timestamp_is_not_treated_as_on_time():
    case = make_case()
    order = make_order(customer_delivery_date=None)
    delivery = DeliveryAgent(NoopDependency(), NoopDependency()).run(
        case, order, use_llm=False
    )
    assert delivery.delivery_timing_verified is False
    assert delivery.is_delivered_late is False
    assert delivery.is_within_estimate is False
    with pytest.raises(ValueError, match="does not match EC_POLICY_V1"):
        PolicyAgent(NoopDependency(), NoopDependency()).run(
            case, order, make_payment(), delivery, use_llm=False
        )


def test_missing_handoff_timestamp_is_not_assumed_to_be_on_time_logistics():
    case = make_case()
    order = make_order(
        carrier_date=None,
        customer_delivery_date="2018-01-07 08:00:00",
        estimated_delivery_date="2018-01-06 00:00:00",
    )
    delivery = DeliveryAgent(NoopDependency(), NoopDependency()).run(
        case, order, use_llm=False
    )
    assert delivery.is_delivered_late is True
    assert delivery.seller_handoff_timing_verified is False
    with pytest.raises(ValueError, match="does not match EC_POLICY_V1"):
        PolicyAgent(NoopDependency(), NoopDependency()).run(
            case, order, make_payment(), delivery, use_llm=False
        )


def test_multi_seller_late_case_assigns_only_violating_seller():
    case = make_case()
    order = make_order(
        customer_delivery_date="2018-01-08 08:00:00",
        estimated_delivery_date="2018-01-06 00:00:00",
        seller_ids=["seller-a", "seller-b"],
        late_handoff_seller_ids=["seller-b"],
    )
    delivery = DeliveryFinding(
        case_id=case.case_id,
        order_id=order.order_id,
        delivery_timing_verified=True,
        is_delivered_late=True,
        is_within_estimate=False,
        seller_handoff_timing_verified=True,
        seller_handoff_late=True,
        late_handoff_seller_ids=["seller-b"],
    )
    decision = PolicyAgent(NoopDependency(), NoopDependency()).run(
        case, order, make_payment(), delivery, use_llm=False
    )
    assert decision.primary_issue == "late_delivery_seller"
    assert [party.party_id for party in decision.responsible_parties] == ["seller-b"]
    assert decision.recommended_refund_brl == 10.0


def test_seller_evidence_is_only_used_for_seller_responsibility():
    for path in OUTPUT_DIR.glob("EC_*.json"):
        output = json.loads(path.read_text(encoding="utf-8"))
        evidence = set(output["evidence_ids"])
        for seller_id in output["affected_entities"]["seller_ids"]:
            seller_evidence = f"seller:{seller_id}" in evidence
            assert seller_evidence is (
                output["assessment"]["primary_issue"] == "late_delivery_seller"
            ), path.name


def test_evidence_sources_are_relevant_to_policy_branch():
    for path in OUTPUT_DIR.glob("EC_*.json"):
        output = json.loads(path.read_text(encoding="utf-8"))
        issue = output["assessment"]["primary_issue"]
        evidence = output["evidence_ids"]
        has_item = any(value.startswith("item:") for value in evidence)
        has_payment = any(value.startswith("payment:") for value in evidence)
        assert has_item is (issue not in {"canceled_order_paid", "unavailable_order_paid"})
        assert has_payment is (
            issue
            not in {"late_delivery_seller", "late_delivery_logistics"}
        )
