from __future__ import annotations

import csv
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from src.config import DATA_DIR, INPUT_DIR
from src.schemas import CaseInput, ItemFact, PaymentFact


CENT = Decimal("0.01")


def money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def money_float(value: Decimal | str | int | float) -> float:
    return float(money(value))


class DataRepository:
    """Read-only, indexed access to the source CSV files used by the agents."""

    def __init__(self, data_dir: Path = DATA_DIR, input_dir: Path = INPUT_DIR):
        self.data_dir = data_dir
        self.input_dir = input_dir
        self.orders: dict[str, dict[str, str]] = {}
        self.items: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.payments: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.sellers: set[str] = set()
        self._load()

    @staticmethod
    def _read_csv(path: Path):
        with path.open("r", encoding="utf-8", newline="") as handle:
            yield from csv.DictReader(handle)

    def _load(self) -> None:
        for row in self._read_csv(self.data_dir / "olist_orders_dataset.csv"):
            self.orders[row["order_id"]] = row
        for row in self._read_csv(self.data_dir / "olist_order_items_dataset.csv"):
            self.items[row["order_id"]].append(row)
        for rows in self.items.values():
            rows.sort(key=lambda row: int(row["order_item_id"]))
        for row in self._read_csv(self.data_dir / "olist_order_payments_dataset.csv"):
            self.payments[row["order_id"]].append(row)
        for rows in self.payments.values():
            rows.sort(key=lambda row: int(row["payment_sequential"]))
        for row in self._read_csv(self.data_dir / "olist_sellers_dataset.csv"):
            self.sellers.add(row["seller_id"])

    def load_cases(self) -> list[CaseInput]:
        cases = []
        for path in sorted(self.input_dir.glob("EC_*.json")):
            with path.open("r", encoding="utf-8") as handle:
                case = CaseInput.model_validate(json.load(handle))
            if case.case_id != path.stem:
                raise ValueError(f"case_id mismatch in {path.name}")
            cases.append(case)
        return cases

    def get_order(self, order_id: str) -> dict[str, str]:
        try:
            return dict(self.orders[order_id])
        except KeyError as exc:
            raise KeyError(f"Order not found: {order_id}") from exc

    def get_items(self, order_id: str) -> list[ItemFact]:
        return [
            ItemFact(
                order_item_id=int(row["order_item_id"]),
                product_id=row["product_id"],
                seller_id=row["seller_id"],
                shipping_limit_date=row["shipping_limit_date"],
                price_brl=money_float(row["price"]),
                freight_brl=money_float(row["freight_value"]),
            )
            for row in self.items.get(order_id, [])
        ]

    def get_payments(self, order_id: str) -> list[PaymentFact]:
        return [
            PaymentFact(
                payment_sequential=int(row["payment_sequential"]),
                payment_type=row["payment_type"],
                payment_installments=int(row["payment_installments"]),
                payment_value_brl=money_float(row["payment_value"]),
            )
            for row in self.payments.get(order_id, [])
        ]

    def evidence_exists(self, evidence_id: str) -> bool:
        parts = evidence_id.split(":")
        kind = parts[0]
        if kind == "order" and len(parts) == 2:
            return parts[1] in self.orders
        if kind == "item" and len(parts) == 3:
            return any(
                row["order_item_id"] == parts[2]
                for row in self.items.get(parts[1], [])
            )
        if kind == "payment" and len(parts) == 3:
            return any(
                row["payment_sequential"] == parts[2]
                for row in self.payments.get(parts[1], [])
            )
        if kind == "seller" and len(parts) == 2:
            return parts[1] in self.sellers
        if kind == "policy" and len(parts) == 2:
            return parts[1] in {
                "SELLER_HANDOFF_AFTER_LIMIT",
                "CARRIER_DELIVERED_AFTER_ESTIMATE",
                "ORDER_CANCELED_AFTER_PAYMENT",
                "ORDER_UNAVAILABLE_AFTER_PAYMENT",
                "MULTIPLE_PAYMENTS_RECONCILED",
                "DELIVERY_WITHIN_ESTIMATE",
            }
        return False
