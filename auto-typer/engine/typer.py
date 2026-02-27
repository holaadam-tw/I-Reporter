"""PyAutoGUI 核心引擎 — 封裝三種輸入方式 + 中文支援"""

import time
import logging

import pyautogui
import pyperclip
from PIL import Image

logger = logging.getLogger("auto_typer")


class TyperEngine:
    """自動輸入引擎，支援座標點擊、Tab 切換、截圖比對三種方式。"""

    def __init__(self, settings: dict):
        cfg = settings.get("pyautogui", {})
        pyautogui.PAUSE = cfg.get("pause", 0.3)
        pyautogui.FAILSAFE = cfg.get("failsafe", True)
        self._typing_interval = cfg.get("typing_interval", 0.05)

    # ── 三種輸入方式 ───────────────────────────────────────

    def click_and_type(
        self, x: int, y: int, text: str, clear_first: bool = True
    ):
        """座標點擊 → 清除原內容 → 輸入文字。"""
        pyautogui.click(x, y)
        if clear_first:
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.05)
        self.type_text(str(text))
        logger.debug("click_and_type (%d,%d) → %s", x, y, text)

    def tab_and_type(self, text: str, tabs: int = 1):
        """按 Tab 切換欄位 → 輸入文字。"""
        for _ in range(tabs):
            pyautogui.press("tab")
            time.sleep(0.05)
        self.type_text(str(text))
        logger.debug("tab_and_type (tabs=%d) → %s", tabs, text)

    def screenshot_click(
        self,
        image_path: str,
        confidence: float = 0.9,
        offset: tuple[int, int] = (0, 0),
        timeout: float = 10.0,
    ):
        """截圖比對 → 點擊匹配位置中心 + offset。"""
        location = self.wait_for_image(image_path, timeout, confidence)
        if location is None:
            raise RuntimeError(f"找不到截圖目標: {image_path}")
        center = pyautogui.center(location)
        pyautogui.click(center.x + offset[0], center.y + offset[1])
        logger.debug(
            "screenshot_click %s → (%d,%d)",
            image_path,
            center.x + offset[0],
            center.y + offset[1],
        )

    # ── 輔助方法 ──────────────────────────────────────────

    def type_text(self, text: str, interval: float | None = None):
        """輸入文字。中文透過剪貼簿貼上，ASCII 用 typewrite。"""
        if not text:
            return
        # 檢查是否含非 ASCII 字元
        if any(ord(c) > 127 for c in text):
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
        else:
            pyautogui.typewrite(
                text, interval=interval or self._typing_interval
            )

    def press_key(self, key: str):
        pyautogui.press(key)

    def hotkey(self, *keys: str):
        pyautogui.hotkey(*keys)

    def wait(self, seconds: float):
        time.sleep(seconds)

    def wait_for_image(
        self,
        image_path: str,
        timeout: float = 10.0,
        confidence: float = 0.9,
    ):
        """等待截圖目標出現，回傳位置或 None。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                location = pyautogui.locateOnScreen(
                    image_path, confidence=confidence
                )
                if location:
                    return location
            except pyautogui.ImageNotFoundException:
                pass
            time.sleep(0.5)
        return None

    @staticmethod
    def get_mouse_position() -> tuple[int, int]:
        """取得目前滑鼠座標（座標擷取工具用）。"""
        pos = pyautogui.position()
        return (pos.x, pos.y)

    @staticmethod
    def take_screenshot(region: tuple[int, int, int, int] | None = None) -> Image.Image:
        """擷取螢幕截圖。"""
        return pyautogui.screenshot(region=region)
