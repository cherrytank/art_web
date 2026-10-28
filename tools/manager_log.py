"""管理器共用紀錄：輪替檔案、台灣時間與常見憑證遮罩。"""
from datetime import datetime, timedelta, timezone
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import tempfile

logger = logging.getLogger("site_manager")
logger.addHandler(logging.NullHandler())
logger.propagate = False
log_path: Path | None = None


def redact(text: str) -> str:
    text = re.sub(r"(https?://)[^\s/@]+(?::[^\s/@]*)?@", r"\1[隱藏憑證]@", text)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)\S+", r"\1[隱藏]", text)
    text = re.sub(r"(?i)((?:token|password|access_token)\s*[=:]\s*)[^\s&]+", r"\1[隱藏]", text)
    return re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "[隱藏權杖]", text)


class SafeFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S +08:00")

    def format(self, record):
        return redact(super().format(record))


def configure(root: Path) -> Path:
    global log_path
    folders = [root / ".codex-work/logs", Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "ShenSiteManager/logs"]
    for folder in folders:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "manager.log"
            handler = RotatingFileHandler(path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
            break
        except OSError:
            continue
    else:
        raise OSError("無法建立管理器紀錄檔，請確認專案或使用者資料夾可寫入。")
    for old in list(logger.handlers):
        logger.removeHandler(old)
        old.close()
    handler.setFormatter(SafeFormatter("%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    log_path = path
    return path


def tail(limit: int = 200_000) -> str:
    if log_path is None:
        return "尚未建立紀錄。"
    try:
        with log_path.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - limit))
            text = stream.read().decode("utf-8", errors="replace")
        return ("（僅顯示最新 200 KB；較早紀錄請開啟資料夾查看）\n" if size > limit else "") + text
    except OSError as error:
        return f"無法讀取紀錄：{error}"
