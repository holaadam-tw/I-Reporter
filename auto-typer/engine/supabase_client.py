"""Supabase REST API 客戶端（使用 httpx）"""

import httpx
import logging

logger = logging.getLogger("auto_typer")

PAGE_SIZE = 1000


class SupabaseClient:
    """透過 PostgREST 與 Supabase 溝通。"""

    def __init__(self, url: str, anon_key: str):
        self.base_url = url.rstrip("/")
        self.rest_url = f"{self.base_url}/rest/v1"
        self.headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers, timeout=30.0
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── 通用方法 ────────────────────────────────────────────

    async def fetch(
        self, table: str, query: str = "", method: str = "GET", body=None
    ):
        """發送單次 REST 請求。"""
        client = await self._get_client()
        url = f"{self.rest_url}/{table}?{query}" if query else f"{self.rest_url}/{table}"

        if method == "GET":
            resp = await client.get(url)
        elif method == "POST":
            resp = await client.post(url, json=body)
        elif method == "PATCH":
            resp = await client.patch(url, json=body)
        elif method == "DELETE":
            resp = await client.delete(url)
        else:
            raise ValueError(f"不支援的 method: {method}")

        resp.raise_for_status()
        return resp.json() if resp.text else None

    async def fetch_all(self, table: str, query: str = "") -> list:
        """自動分頁取得所有資料（每頁 1000 筆）。"""
        client = await self._get_client()
        all_rows = []
        offset = 0

        while True:
            sep = "&" if query else ""
            paged_query = f"{query}{sep}limit={PAGE_SIZE}&offset={offset}"
            url = f"{self.rest_url}/{table}?{paged_query}"

            resp = await client.get(url)
            resp.raise_for_status()
            rows = resp.json()
            all_rows.extend(rows)

            if len(rows) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        return all_rows

    async def patch(self, table: str, query: str, body: dict):
        return await self.fetch(table, query, method="PATCH", body=body)

    async def insert(self, table: str, body: dict | list):
        return await self.fetch(table, method="POST", body=body)

    async def rpc(self, fn_name: str, params: dict | None = None) -> list:
        """呼叫 Supabase RPC 函數。"""
        client = await self._get_client()
        url = f"{self.rest_url}/rpc/{fn_name}"
        resp = await client.post(url, json=params or {})
        resp.raise_for_status()
        return resp.json() if resp.text else []

    # ── 業務方法 ────────────────────────────────────────────

    async def fetch_assembly_orders(
        self, date_from: str, date_to: str, only_approved: bool = True
    ) -> list:
        """取得組裝單（含品項及產品資訊）。"""
        query = (
            "select=*,assembly_items(*,products(product_id,product_name))"
            f"&order_date=gte.{date_from}"
            f"&order_date=lte.{date_to}"
            "&order=order_date.desc"
        )
        if only_approved:
            query += "&status=eq.approved"
        return await self.fetch_all("assembly_orders", query)

    async def fetch_packaging_orders(
        self, date_from: str, date_to: str, only_approved: bool = True
    ) -> list:
        """取得包裝單（含品項、產品、客戶資訊）。"""
        query = (
            "select=*,packaging_items(*,products(product_id,product_name)),customers(name,customer_code)"
            f"&order_date=gte.{date_from}"
            f"&order_date=lte.{date_to}"
            "&order=order_date.desc"
        )
        if only_approved:
            query += "&status=eq.approved"
        return await self.fetch_all("packaging_orders", query)

    async def fetch_customers(self) -> list:
        return await self.fetch_all("customers", "order=name.asc")

    async def fetch_products(self) -> list:
        return await self.fetch_all("products", "order=product_id.asc")

    # ── sync_log 操作 ──────────────────────────────────────

    async def log_sync(
        self,
        table_name: str,
        record_id: str,
        target_system: str = "ERP",
        status: str = "success",
        error_msg: str | None = None,
    ):
        """寫入同步記錄。"""
        body = {
            "table_name": table_name,
            "record_id": record_id,
            "target_system": target_system,
            "status": status,
        }
        if error_msg:
            body["error_message"] = error_msg
        try:
            await self.insert("sync_log", body)
        except Exception as e:
            logger.error("寫入 sync_log 失敗: %s", e)

    async def get_synced_ids(
        self, table_name: str, target_system: str = "ERP"
    ) -> set[str]:
        """取得已成功同步的 record_id 集合。"""
        query = (
            "select=record_id"
            f"&table_name=eq.{table_name}"
            f"&target_system=eq.{target_system}"
            "&status=eq.success"
        )
        rows = await self.fetch_all("sync_log", query)
        return {r["record_id"] for r in rows}
