"""自動登打引擎 v1.0 — CustomTkinter GUI 主程式"""

import asyncio
import os
import sys
import threading
import queue
import logging
from datetime import date

import yaml
import customtkinter as ctk

# 確保 auto-typer/ 可以作為 package root
sys.path.insert(0, os.path.dirname(__file__))

from engine.logger import setup_logger
from engine.supabase_client import SupabaseClient
from engine.typer import TyperEngine
from engine.safety import SafetyManager, StoppedException
from flows.erp_assembly import ERPAssemblyFlow
from flows.erp_packaging import ERPPackagingFlow

# ── 全域設定 ────────────────────────────────────────────────

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── 主視窗 ──────────────────────────────────────────────────

class AutoTyperApp(ctk.CTk):
    """自動登打引擎 GUI。"""

    FLOWS = {
        "ERP 組裝單": ERPAssemblyFlow,
        "ERP 包裝單": ERPPackagingFlow,
    }

    def __init__(self):
        super().__init__()

        # 設定
        self.settings = load_yaml(os.path.join(CONFIG_DIR, "settings.yaml"))
        self.erp_config = load_yaml(os.path.join(CONFIG_DIR, "erp_config.yaml"))
        self.logger = setup_logger(
            max_files=self.settings.get("logging", {}).get("max_files", 30)
        )

        # 元件
        self.supabase: SupabaseClient | None = None
        self.typer = TyperEngine(self.settings)
        self.safety = SafetyManager(self.settings)
        self.safety.on_status_change = self._on_safety_status

        # 狀態
        self._running = False
        self._msg_queue: queue.Queue = queue.Queue()
        self._preview_data: list = []

        # GUI
        self.title("自動登打引擎 v1.0")
        self.geometry("640x720")
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._build_ui()
        self._init_supabase()
        self._poll_queue()

    # ── UI 建構 ──────────────────────────────────────────

    def _build_ui(self):
        # 頂部 — 流程 + 日期
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(top, text="流程:").grid(row=0, column=0, padx=(8, 4), pady=8)
        self.flow_var = ctk.StringVar(value=list(self.FLOWS.keys())[0])
        self.flow_menu = ctk.CTkOptionMenu(
            top, variable=self.flow_var, values=list(self.FLOWS.keys()), width=180
        )
        self.flow_menu.grid(row=0, column=1, padx=4, pady=8)

        ctk.CTkLabel(top, text="日期:").grid(row=0, column=2, padx=(16, 4), pady=8)
        today = date.today().isoformat()
        self.date_from_var = ctk.StringVar(value=today)
        self.date_from_entry = ctk.CTkEntry(top, textvariable=self.date_from_var, width=120, placeholder_text="YYYY-MM-DD")
        self.date_from_entry.grid(row=0, column=3, padx=2, pady=8)

        ctk.CTkLabel(top, text="~").grid(row=0, column=4, padx=2, pady=8)
        self.date_to_var = ctk.StringVar(value=today)
        self.date_to_entry = ctk.CTkEntry(top, textvariable=self.date_to_var, width=120, placeholder_text="YYYY-MM-DD")
        self.date_to_entry.grid(row=0, column=5, padx=2, pady=8)

        self.load_btn = ctk.CTkButton(top, text="載入資料", width=90, command=self._on_load)
        self.load_btn.grid(row=0, column=6, padx=(8, 8), pady=8)

        # 中間 — 資料預覽
        preview_frame = ctk.CTkFrame(self)
        preview_frame.pack(fill="both", expand=True, padx=12, pady=6)

        ctk.CTkLabel(preview_frame, text="資料預覽", anchor="w", font=ctk.CTkFont(weight="bold")).pack(
            fill="x", padx=8, pady=(8, 2)
        )

        # 表頭
        header_frame = ctk.CTkFrame(preview_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=8)
        for col, w in [("單號", 160), ("日期", 100), ("品項數", 70), ("狀態", 80)]:
            ctk.CTkLabel(header_frame, text=col, width=w, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(
                side="left", padx=2
            )

        self.preview_scroll = ctk.CTkScrollableFrame(preview_frame, height=160)
        self.preview_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self.preview_summary = ctk.CTkLabel(preview_frame, text="尚未載入資料", anchor="w")
        self.preview_summary.pack(fill="x", padx=8, pady=(0, 8))

        # 控制列
        ctrl = ctk.CTkFrame(self)
        ctrl.pack(fill="x", padx=12, pady=6)

        self.start_btn = ctk.CTkButton(ctrl, text="▶ 開始", width=100, command=self._on_start, state="disabled")
        self.start_btn.pack(side="left", padx=(8, 4), pady=8)

        self.pause_btn = ctk.CTkButton(ctrl, text="⏸ 暫停", width=100, command=self._on_pause, state="disabled")
        self.pause_btn.pack(side="left", padx=4, pady=8)

        self.stop_btn = ctk.CTkButton(
            ctrl, text="⏹ 停止", width=100, fg_color="#c0392b", hover_color="#e74c3c",
            command=self._on_stop, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=4, pady=8)

        # 座標工具按鈕
        self.coord_btn = ctk.CTkButton(
            ctrl, text="座標擷取", width=90, fg_color="#7f8c8d", hover_color="#95a5a6",
            command=self._on_coord_tool
        )
        self.coord_btn.pack(side="right", padx=(4, 8), pady=8)

        self.progress_bar = ctk.CTkProgressBar(ctrl, width=400)
        self.progress_bar.pack(fill="x", padx=8, pady=(0, 4))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(ctrl, text="進度: 0/0", anchor="w")
        self.progress_label.pack(fill="x", padx=8, pady=(0, 8))

        # 底部 — 執行日誌
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        ctk.CTkLabel(log_frame, text="執行日誌", anchor="w", font=ctk.CTkFont(weight="bold")).pack(
            fill="x", padx=8, pady=(8, 2)
        )

        self.log_box = ctk.CTkTextbox(log_frame, height=140, state="disabled", font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        # 狀態列
        self.status_label = ctk.CTkLabel(
            self, text="F9=暫停  F10=中止  |  連線: 未連線", anchor="w",
            font=ctk.CTkFont(size=11), text_color="#95a5a6"
        )
        self.status_label.pack(fill="x", padx=16, pady=(0, 8))

    # ── 初始化 ───────────────────────────────────────────

    def _init_supabase(self):
        supa_cfg = self.settings.get("supabase", {})
        url = supa_cfg.get("url", "")
        key = supa_cfg.get("anon_key", "")
        if url and key:
            self.supabase = SupabaseClient(url, key)
            self._update_status("連線: 已設定")
            self.logger.info("Supabase 已連線: %s", url)
        else:
            self._update_status("連線: 請先填入 config/settings.yaml 的 anon_key")
            self.logger.warning("Supabase anon_key 未設定")

    # ── 事件處理 ─────────────────────────────────────────

    def _on_load(self):
        """載入資料按鈕。"""
        if not self.supabase:
            self._append_log("[ERR] Supabase 未連線，請設定 anon_key")
            return

        self.load_btn.configure(state="disabled", text="載入中...")
        date_from = self.date_from_var.get()
        date_to = self.date_to_var.get()
        flow_name = self.flow_var.get()

        def do_load():
            loop = asyncio.new_event_loop()
            try:
                flow_cls = self.FLOWS[flow_name]
                flow = flow_cls(self.typer, self.supabase, self.safety, self.erp_config, self.logger)
                data = loop.run_until_complete(flow.fetch_data(date_from, date_to))
                synced = loop.run_until_complete(self.supabase.get_synced_ids(flow.table_name))
                self._msg_queue.put(("loaded", data, synced, flow.table_name))
            except Exception as e:
                self._msg_queue.put(("error", f"載入失敗: {e}"))
            finally:
                loop.close()

        threading.Thread(target=do_load, daemon=True).start()

    def _on_start(self):
        """開始執行。"""
        if self._running:
            return
        self._running = True
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.load_btn.configure(state="disabled")

        self.safety.reset()
        self.safety.start()

        date_from = self.date_from_var.get()
        date_to = self.date_to_var.get()
        flow_name = self.flow_var.get()

        def do_run():
            loop = asyncio.new_event_loop()
            try:
                flow_cls = self.FLOWS[flow_name]
                flow = flow_cls(self.typer, self.supabase, self.safety, self.erp_config, self.logger)

                def on_progress(current, total, msg):
                    self._msg_queue.put(("progress", current, total, msg))

                stats = loop.run_until_complete(flow.run(date_from, date_to, on_progress))
                self._msg_queue.put(("done", stats))
            except Exception as e:
                self._msg_queue.put(("error", f"執行異常: {e}"))
            finally:
                loop.close()

        threading.Thread(target=do_run, daemon=True).start()

    def _on_pause(self):
        self.safety.on_pause()

    def _on_stop(self):
        self.safety.on_stop()

    def _on_coord_tool(self):
        """座標擷取工具 — 彈出小視窗，即時顯示滑鼠位置。"""
        CoordToolWindow(self, self.typer)

    def _on_safety_status(self, status: str):
        """SafetyManager 狀態回呼。"""
        self._msg_queue.put(("safety_status", status))

    # ── 佇列處理 ─────────────────────────────────────────

    def _poll_queue(self):
        """定期從佇列取出訊息更新 GUI。"""
        try:
            while True:
                msg = self._msg_queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_msg(self, msg):
        kind = msg[0]

        if kind == "loaded":
            _, data, synced, table_name = msg
            self._preview_data = data
            self._render_preview(data, synced)
            self.load_btn.configure(state="normal", text="載入資料")
            if data:
                self.start_btn.configure(state="normal")

        elif kind == "progress":
            _, current, total, text = msg
            self.progress_bar.set(current / total if total else 0)
            self.progress_label.configure(text=f"進度: {current}/{total}")
            self._append_log(text)

        elif kind == "done":
            _, stats = msg
            self._running = False
            self.safety.stop()
            self.start_btn.configure(state="normal")
            self.pause_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled")
            self.load_btn.configure(state="normal")
            summary = f"完成 — 成功: {stats['success']}  失敗: {stats['failed']}  略過: {stats['skipped']}"
            self._append_log(summary)
            self._update_status(f"F9=暫停  F10=中止  |  {summary}")

        elif kind == "error":
            _, text = msg
            self._append_log(f"[ERR] {text}")
            self._running = False
            self.safety.stop()
            self.start_btn.configure(state="normal" if self._preview_data else "disabled")
            self.pause_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled")
            self.load_btn.configure(state="normal", text="載入資料")

        elif kind == "safety_status":
            _, status = msg
            if status == "paused":
                self.pause_btn.configure(text="▶ 繼續")
                self._append_log("⏸ 已暫停")
            elif status == "running":
                self.pause_btn.configure(text="⏸ 暫停")
                self._append_log("▶ 已繼續")
            elif status == "stopped":
                self._append_log("⏹ 已中止")

    # ── UI 更新輔助 ──────────────────────────────────────

    def _render_preview(self, data: list, synced: set):
        """渲染資料預覽表格。"""
        # 清除舊內容
        for widget in self.preview_scroll.winfo_children():
            widget.destroy()

        for row in data:
            row_frame = ctk.CTkFrame(self.preview_scroll, fg_color="transparent")
            row_frame.pack(fill="x", pady=1)

            order_no = str(row.get("order_no", row.get("id", "?")[:12]))
            order_date = str(row.get("order_date", ""))
            items = row.get("assembly_items") or row.get("packaging_items") or []
            item_count = str(len(items))
            is_synced = row.get("id") in synced
            status_text = "已同步" if is_synced else "待同步"
            status_color = "#27ae60" if is_synced else "#f39c12"

            ctk.CTkLabel(row_frame, text=order_no, width=160, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left", padx=2)
            ctk.CTkLabel(row_frame, text=order_date, width=100, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left", padx=2)
            ctk.CTkLabel(row_frame, text=item_count, width=70, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left", padx=2)
            ctk.CTkLabel(
                row_frame, text=status_text, width=80, anchor="w",
                font=ctk.CTkFont(size=12), text_color=status_color
            ).pack(side="left", padx=2)

        synced_count = sum(1 for r in data if r.get("id") in synced)
        pending_count = len(data) - synced_count
        self.preview_summary.configure(
            text=f"共 {len(data)} 筆，已同步 {synced_count} 筆，待同步 {pending_count} 筆"
        )

    def _append_log(self, text: str):
        """新增一行到日誌。"""
        from datetime import datetime

        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{timestamp} {text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _update_status(self, text: str):
        self.status_label.configure(text=f"F9=暫停  F10=中止  |  {text}")


# ── 座標擷取工具視窗 ────────────────────────────────────────

class CoordToolWindow(ctk.CTkToplevel):
    """小工具：即時顯示滑鼠座標。"""

    def __init__(self, parent, typer: TyperEngine):
        super().__init__(parent)
        self.typer = typer
        self.title("座標擷取工具")
        self.geometry("280x120")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self.coord_label = ctk.CTkLabel(
            self, text="X: 0  Y: 0", font=ctk.CTkFont(size=20, weight="bold")
        )
        self.coord_label.pack(pady=(16, 8))

        ctk.CTkLabel(self, text="移動滑鼠查看座標，關閉此視窗結束", font=ctk.CTkFont(size=11), text_color="#95a5a6").pack()

        self._updating = True
        self._update_coords()

    def _update_coords(self):
        if not self._updating or not self.winfo_exists():
            return
        x, y = self.typer.get_mouse_position()
        self.coord_label.configure(text=f"X: {x}  Y: {y}")
        self.after(50, self._update_coords)

    def destroy(self):
        self._updating = False
        super().destroy()


# ── 入口 ────────────────────────────────────────────────────

if __name__ == "__main__":
    app = AutoTyperApp()
    app.mainloop()
