"""流程基底類別 — 定義登打流程的標準介面"""

import logging
from abc import ABC, abstractmethod
from typing import Callable

from engine.supabase_client import SupabaseClient
from engine.typer import TyperEngine
from engine.safety import SafetyManager, StoppedException

logger = logging.getLogger("auto_typer")


class BaseFlow(ABC):
    """所有登打流程的抽象基底類別。"""

    def __init__(
        self,
        typer: TyperEngine,
        supabase: SupabaseClient,
        safety: SafetyManager,
        config: dict,
        flow_logger: logging.Logger | None = None,
    ):
        self.typer = typer
        self.supabase = supabase
        self.safety = safety
        self.config = config
        self.logger = flow_logger or logger

    @property
    @abstractmethod
    def name(self) -> str:
        """流程名稱。"""

    @property
    @abstractmethod
    def table_name(self) -> str:
        """對應的 Supabase 資料表名稱（用於 sync_log）。"""

    @abstractmethod
    async def fetch_data(self, date_from: str, date_to: str) -> list:
        """從 Supabase 取得待登打資料。"""

    @abstractmethod
    def setup(self):
        """開啟/定位 ERP 視窗。"""

    @abstractmethod
    def process_row(self, row: dict):
        """處理單筆資料。"""

    @abstractmethod
    def teardown(self):
        """收尾（儲存、關閉）。"""

    def get_row_display(self, row: dict) -> str:
        """取得單筆資料的顯示文字（用於 GUI 日誌）。"""
        return row.get("id", "?")[:12]

    async def run(
        self,
        date_from: str,
        date_to: str,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """執行登打流程。

        Args:
            on_progress: (current, total, message) 回呼

        Returns:
            {"total": int, "success": int, "failed": int, "skipped": int}
        """
        stats = {"total": 0, "success": 0, "failed": 0, "skipped": 0}

        # 1. 取得資料
        self.logger.info("[%s] 載入資料 %s ~ %s", self.name, date_from, date_to)
        data = await self.fetch_data(date_from, date_to)
        self.logger.info("[%s] 共 %d 筆資料", self.name, len(data))

        if not data:
            return stats

        # 2. 過濾已同步
        synced_ids = await self.supabase.get_synced_ids(self.table_name)
        data = [r for r in data if r.get("id") not in synced_ids]
        stats["skipped"] = len(synced_ids)
        stats["total"] = len(data)
        self.logger.info(
            "[%s] 過濾已同步後剩 %d 筆（已同步 %d 筆）",
            self.name,
            len(data),
            len(synced_ids),
        )

        if not data:
            return stats

        # 3. 設定 ERP 環境
        self.setup()

        # 4. 逐筆處理
        for i, row in enumerate(data):
            row_label = self.get_row_display(row)

            try:
                self.safety.check()
                self.process_row(row)
                await self.supabase.log_sync(
                    self.table_name, row["id"], status="success"
                )
                stats["success"] += 1
                msg = f"[OK] {row_label}"
                self.logger.info(msg)

            except StoppedException:
                self.logger.warning("使用者中止，已處理 %d/%d", i, len(data))
                break

            except Exception as e:
                await self.supabase.log_sync(
                    self.table_name,
                    row["id"],
                    status="failed",
                    error_msg=str(e),
                )
                stats["failed"] += 1
                msg = f"[ERR] {row_label}: {e}"
                self.logger.error(msg)

            if on_progress:
                on_progress(i + 1, len(data), msg)

        # 5. 收尾
        self.teardown()
        self.logger.info(
            "[%s] 完成: 成功 %d / 失敗 %d / 略過 %d",
            self.name,
            stats["success"],
            stats["failed"],
            stats["skipped"],
        )
        return stats
