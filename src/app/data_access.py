from __future__ import annotations

from pathlib import Path
from typing import Any


import json
from langchain_core.tools import tool


class ShoppingDataStore:
    """Student scaffold for mock-data lookup."""

    def __init__(self, json_path: Path) -> None:
        if not json_path.exists():
            raise FileNotFoundError(f"JSON data file not found at {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.metadata = data.get("metadata", {})
        self.customers_list = data.get("customers", [])
        self.orders_list = data.get("orders", [])
        self.vouchers_list = data.get("vouchers", [])

        # Build fast lookup indexes
        self.customer_by_id = {
            c["customer_id"].strip(): c 
            for c in self.customers_list 
            if "customer_id" in c
        }
        self.order_by_id = {
            str(o["order_id"]).strip(): o 
            for o in self.orders_list 
            if "order_id" in o
        }

        self.orders_by_customer_id = {}
        for o in self.orders_list:
            c_id = o.get("customer_id")
            if c_id:
                self.orders_by_customer_id.setdefault(c_id.strip(), []).append(o)

        self.vouchers_by_customer_id = {}
        for v in self.vouchers_list:
            c_id = v.get("customer_id")
            if c_id:
                self.vouchers_by_customer_id.setdefault(c_id.strip(), []).append(v)

    def get_customer_by_id(self, customer_id: str) -> dict[str, Any]:
        cid = str(customer_id).strip()
        if cid in self.customer_by_id:
            return {"status": "ok", "customer": self.customer_by_id[cid]}
        return {"status": "not_found", "customer_id": cid}

    def get_orders_by_customer_id(self, customer_id: str, limit: int = 10) -> dict[str, Any]:
        cid = str(customer_id).strip()
        if cid not in self.customer_by_id:
            return {"status": "not_found", "customer_id": cid}
        orders = self.orders_by_customer_id.get(cid, [])
        sorted_orders = sorted(orders, key=lambda x: x.get("created_at", ""), reverse=True)
        return {"status": "ok", "orders": sorted_orders[:limit]}

    def get_order_detail_by_order_id(self, order_id: str) -> dict[str, Any]:
        oid = str(order_id).strip()
        if oid in self.order_by_id:
            return {"status": "ok", "order": self.order_by_id[oid]}
        return {"status": "not_found", "order_id": oid}

    def get_vouchers_by_customer_id(
        self,
        customer_id: str,
        only_active: bool = False,
    ) -> dict[str, Any]:
        cid = str(customer_id).strip()
        if cid not in self.customer_by_id:
            return {"status": "not_found", "customer_id": cid}
        vouchers = self.vouchers_by_customer_id.get(cid, [])
        if only_active:
            vouchers = [v for v in vouchers if v.get("status") == "active"]
        return {"status": "ok", "vouchers": vouchers}


def build_data_tools(store: ShoppingDataStore) -> list:
    @tool
    def get_customer_by_id(customer_id: str) -> dict[str, Any]:
        """Lấy thông tin cá nhân và hạng thành viên của khách hàng dựa trên mã khách hàng customer_id (ví dụ: 'C001')."""
        return store.get_customer_by_id(customer_id)

    @tool
    def get_orders_by_customer_id(customer_id: str) -> dict[str, Any]:
        """Lấy danh sách các đơn hàng gần đây của khách hàng dựa trên mã khách hàng customer_id (ví dụ: 'C001')."""
        return store.get_orders_by_customer_id(customer_id)

    @tool
    def get_order_detail_by_order_id(order_id: str) -> dict[str, Any]:
        """Lấy chi tiết trạng thái, ngày giao hàng dự kiến, sản phẩm và tính hợp lệ trả hàng của một đơn cụ thể dựa trên mã đơn hàng order_id (ví dụ: '1971', '2058')."""
        return store.get_order_detail_by_order_id(order_id)

    @tool
    def get_vouchers_by_customer_id(customer_id: str) -> dict[str, Any]:
        """Lấy danh sách tất cả mã giảm giá (vouchers) của một khách hàng dựa trên mã khách hàng customer_id (ví dụ: 'C001')."""
        return store.get_vouchers_by_customer_id(customer_id)

    return [
        get_customer_by_id,
        get_orders_by_customer_id,
        get_order_detail_by_order_id,
        get_vouchers_by_customer_id,
    ]

