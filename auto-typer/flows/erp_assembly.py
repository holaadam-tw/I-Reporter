"""ERP 組裝單登打流程"""

import os
import logging

from flows.base_flow import BaseFlow

logger = logging.getLogger("auto_typer")

SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")


class ERPAssemblyFlow(BaseFlow):
    """組裝單 → ERP 自動登打。"""

    @property
    def name(self) -> str:
        return "ERP 組裝單登打"

    @property
    def table_name(self) -> str:
        return "assembly_orders"

    async def fetch_data(self, date_from: str, date_to: str) -> list:
        return await self.supabase.fetch_assembly_orders(date_from, date_to)

    def setup(self):
        """定位 ERP 視窗。"""
        erp_cfg = self.config.get("erp", {})
        window_title = erp_cfg.get("window_title", "ERP System")
        self.logger.info("定位 ERP 視窗: %s", window_title)
        # 使用者需依實際 ERP 軟體調整此處邏輯
        self.typer.wait(1)

    def process_row(self, row: dict):
        """依 erp_config.yaml 定義的步驟執行單筆組裝單登打。"""
        erp_cfg = self.config.get("erp", {})
        assembly_cfg = erp_cfg.get("assembly", {})
        steps = assembly_cfg.get("steps", [])
        item_steps = assembly_cfg.get("item_steps", [])
        save_step = assembly_cfg.get("save_step")

        # 執行主單步驟
        for step in steps:
            self.safety.check()
            self._execute_step(step, row)

        # 處理子項目
        items = row.get("assembly_items", [])
        for item in items:
            for step in item_steps:
                self.safety.check()
                self._execute_step(step, item)

        # 儲存
        if save_step:
            self.safety.check()
            self._execute_step(save_step, row)
            self.typer.wait(0.5)

    def teardown(self):
        self.logger.info("[%s] 登打完成", self.name)

    def get_row_display(self, row: dict) -> str:
        order_no = row.get("order_no", row.get("id", "?")[:12])
        return str(order_no)

    # ── 內部方法 ──────────────────────────────────────────

    def _execute_step(self, step: dict, data: dict):
        """執行單一步驟。"""
        action = step.get("action")
        desc = step.get("desc", "")

        if action == "click_and_type":
            field = step.get("field", "")
            text = self._resolve_field(field, data)
            self.typer.click_and_type(step["x"], step["y"], text)
            self.logger.debug("  %s: %s → %s", action, desc, text)

        elif action == "tab_and_type":
            field = step.get("field", "")
            text = self._resolve_field(field, data)
            tabs = step.get("tabs", 1)
            self.typer.tab_and_type(text, tabs)
            self.logger.debug("  %s: %s → %s", action, desc, text)

        elif action == "screenshot_click":
            image = step.get("image", "")
            image_path = os.path.join(SCREENSHOTS_DIR, image)
            confidence = step.get("confidence", 0.9)
            offset = tuple(step.get("offset", [0, 0]))
            self.typer.screenshot_click(image_path, confidence, offset)
            self.logger.debug("  %s: %s", action, desc)

        elif action == "press_key":
            self.typer.press_key(step.get("key", "enter"))

        elif action == "wait":
            self.typer.wait(step.get("seconds", 0.5))

        else:
            self.logger.warning("未知的 action: %s", action)

    @staticmethod
    def _resolve_field(field: str, data: dict) -> str:
        """從 data dict 解析欄位值。支援巢狀如 products.product_id。"""
        if not field:
            return ""
        parts = field.split(".")
        value = data
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part, "")
            else:
                return ""
        return str(value) if value is not None else ""
