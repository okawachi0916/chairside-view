"""データベース。場所は環境変数 CV_DATA_DIR、無ければリポジトリの data/runtime。"""
import os
import sqlite3
from pathlib import Path

from app.db.initial import age_on  # noqa: F401  (他の窓から使う)


def data_dir() -> Path:
    d = os.environ.get("CV_DATA_DIR")
    return Path(d) if d else Path(__file__).resolve().parents[2] / "data" / "runtime"


def db_path() -> Path:
    return data_dir() / "app.db"


def connect(path=None, align=True) -> sqlite3.Connection:
    """データベースを開く。開くたびに、見本の日付が「今日」に合っているかを通す（app/db/dates.py。同じ日の2回目からは調べない）。
    align=False は、見本を作る・足す update() と、中身を写すだけの道具が使う。"""
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    if align:
        from app.db import dates  # initial → today の読み込みと重ならないよう、使うときに読む

        try:
            dates.ensure(con, p)
        except Exception:
            con.close()
            raise
    return con
