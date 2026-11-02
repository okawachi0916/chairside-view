"""データベース。場所は環境変数 CV_DATA_DIR、無ければリポジトリの data/runtime。"""
import os
import sqlite3
from pathlib import Path

from app.db.initial import TODAY, age_on  # noqa: F401  (他の窓から使う)


def data_dir() -> Path:
    d = os.environ.get("CV_DATA_DIR")
    return Path(d) if d else Path(__file__).resolve().parents[2] / "data" / "runtime"


def db_path() -> Path:
    return data_dir() / "app.db"


def connect(path=None) -> sqlite3.Connection:
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con
