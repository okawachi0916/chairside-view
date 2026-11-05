"""写真の置き場。一覧は data/photos/photos.json。置き場は環境変数 CV_PHOTO_DIR で変えられる。
患者様の中の番号 n の写真は、一覧の ((n-1) 番目 mod 件数) 番目の画像を使う（仮の写真。あとで差し替える）。"""
import json
import os
from pathlib import Path

from app import errlog

ROOT = Path(__file__).resolve().parents[2]


def photo_dir() -> Path:
    return Path(os.environ.get("CV_PHOTO_DIR") or ROOT / "data" / "photos")


_reported = set()


def _load() -> dict:
    """一覧を読む。無いときは写真が無いだけ（空で続ける）。壊れているときは、理由を1回だけ記録に残して空で続ける。"""
    p = photo_dir() / "photos.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("一覧の形が違います")
        return data
    except FileNotFoundError:
        key, what, exc = "none", f"写真の一覧がありません（{p}）。写真は0件で続けます", None
    except Exception as e:  # noqa: BLE001
        key, what, exc = "broken", f"写真の一覧が読めません（{p}）。写真は0件で続けます", e
    if key not in _reported:
        _reported.add(key)
        errlog.record("写真の一覧", what, exc)
    return {}


def listing() -> list:
    return _load().get("photos", [])


def cards() -> list:
    """診察券（受付の画面）の画像。裏面の2枚。"""
    return _load().get("cards", [])


def card_urls() -> list:
    return ["/photo-files/" + x["file"] for x in cards()]


def url_for(number: int, file: str = "") -> str:
    """スマホから入れた写真（file がある）はその画像、無ければ仮の写真。"""
    if file:
        return "/photo-up/" + file
    items = listing()
    if not items:
        return ""
    return "/photo-files/" + items[(int(number) - 1) % len(items)]["file"]
