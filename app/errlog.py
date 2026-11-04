"""失敗の記録。黙って飲み込まず、いつ・どこで・何が起きたかを data/runtime/error_log.txt に1行ずつ残す（患者様の名前や記録の中身は書かない）。"""
import logging
import threading
import traceback
from datetime import datetime

from app.db import data_dir

_lock = threading.Lock()
log = logging.getLogger("chairside")


def record(where: str, what: str, exc: BaseException | None = None) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} [{where}] {what}"
    if exc is not None:
        line += f" ({type(exc).__name__}: {str(exc)[:120]})"
        log.error(line + "\n" + "".join(traceback.format_exception(exc)[-3:]))
    else:
        log.warning(line)
    try:
        d = data_dir()
        d.mkdir(parents=True, exist_ok=True)
        with _lock, (d / "error_log.txt").open("a", encoding="utf-8") as f:
            f.write(line.replace("\n", " ") + "\n")
    except OSError:
        pass  # 記録の書き込みが失敗しても、本来の処理は続ける（ログには出ている）


def read_recent(n: int = 20) -> list:
    p = data_dir() / "error_log.txt"
    try:
        return p.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
