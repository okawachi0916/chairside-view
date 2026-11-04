"""アプリの「今日」を決める唯一の場所。既定はパソコンの日付。撮影で日付を止めたいときは、環境変数 CV_TODAY=2026-11-06 のように指す。"""
import os
from datetime import date

WEEK = "月火水木金土日"
BASE = "2026-11-06"  # 見本データを書いたときの「今日」。見本の過去の日付はここからの差を保って今日に合わせる


def today() -> str:
    v = (os.environ.get("CV_TODAY") or "").strip()
    if v:
        try:
            return date.fromisoformat(v).isoformat()
        except ValueError:
            pass
    return date.today().isoformat()


def ja_date(s: str, week: bool = False) -> str:
    d = date.fromisoformat(s)
    out = f"{d.year}年{d.month}月{d.day}日"
    return out + f" {WEEK[d.weekday()]}曜日" if week else out


def short_date(s: str) -> str:
    """11月6日(金)"""
    d = date.fromisoformat(s)
    return f"{d.month}月{d.day}日({WEEK[d.weekday()]})"
