"""安全機制 — 暫停、中止、視窗焦點檢查"""

import threading
import logging
import ctypes
from typing import Callable

import keyboard

logger = logging.getLogger("auto_typer")


class StoppedException(Exception):
    """使用者按下中止熱鍵時拋出。"""


class SafetyManager:
    """管理暫停/中止熱鍵 + 視窗焦點檢查。"""

    def __init__(self, settings: dict):
        cfg = settings.get("safety", {})
        self._hotkey_pause = cfg.get("hotkey_pause", "F9")
        self._hotkey_stop = cfg.get("hotkey_stop", "F10")
        self._focus_check_enabled = cfg.get("focus_check", True)

        self.paused = False
        self.stopped = False
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始為非暫停

        self.on_status_change: Callable[[str], None] | None = None

    def start(self):
        """註冊熱鍵。"""
        keyboard.on_press_key(self._hotkey_pause, lambda _: self.on_pause())
        keyboard.on_press_key(self._hotkey_stop, lambda _: self.on_stop())
        logger.info(
            "安全機制啟動: %s=暫停, %s=中止",
            self._hotkey_pause,
            self._hotkey_stop,
        )

    def stop(self):
        """解除熱鍵。"""
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        # 確保暫停中的 thread 能被釋放
        self._pause_event.set()
        logger.info("安全機制已停止")

    def reset(self):
        """重置狀態（用於下一次執行前）。"""
        with self._lock:
            self.paused = False
            self.stopped = False
            self._pause_event.set()

    def check(self):
        """每個動作前呼叫。暫停時阻塞，中止時拋出 StoppedException。"""
        with self._lock:
            if self.stopped:
                raise StoppedException("使用者中止執行")

        # 暫停時阻塞
        self._pause_event.wait()

        # 再次檢查（可能在暫停期間被中止）
        with self._lock:
            if self.stopped:
                raise StoppedException("使用者中止執行")

    def on_pause(self):
        """F9 回呼：切換暫停狀態。"""
        with self._lock:
            self.paused = not self.paused
            if self.paused:
                self._pause_event.clear()
                status = "paused"
                logger.info("⏸ 已暫停（按 %s 繼續）", self._hotkey_pause)
            else:
                self._pause_event.set()
                status = "running"
                logger.info("▶ 已繼續執行")

        if self.on_status_change:
            self.on_status_change(status)

    def on_stop(self):
        """F10 回呼：中止執行。"""
        with self._lock:
            self.stopped = True
            self._pause_event.set()  # 解除暫停阻塞
            logger.info("⏹ 使用者中止執行")

        if self.on_status_change:
            self.on_status_change("stopped")

    def check_focus(self, window_title: str) -> bool:
        """檢查目標視窗是否在前景（Windows only）。"""
        if not self._focus_check_enabled:
            return True
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return window_title.lower() in buf.value.lower()
        except Exception:
            return True  # 無法判斷時不阻塞
