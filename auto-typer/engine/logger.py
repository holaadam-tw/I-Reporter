"""日誌記錄器 — 同時輸出到 console 與檔案"""

import logging
import os
import glob
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


def setup_logger(name: str = "auto_typer", max_files: int = 30) -> logging.Logger:
    """建立 logger，輸出到 console + logs/ 目錄檔案。

    Args:
        name: logger 名稱
        max_files: 保留的最大日誌檔數量
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # 已初始化過，避免重複加 handler

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, f"auto_typer_{timestamp}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 清理舊日誌
    _cleanup_old_logs(max_files)

    logger.info("Logger 初始化完成 → %s", log_file)
    return logger


def _cleanup_old_logs(max_files: int):
    """刪除超過 max_files 數量的舊日誌檔。"""
    pattern = os.path.join(LOG_DIR, "auto_typer_*.log")
    files = sorted(glob.glob(pattern))
    if len(files) > max_files:
        for f in files[: len(files) - max_files]:
            try:
                os.remove(f)
            except OSError:
                pass
