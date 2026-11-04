"""写真の置き場。一覧は data/photos/photos.json。置き場は環境変数 CV_PHOTO_DIR で変えられる。
患者様の中の番号 n の写真は、一覧の ((n-1) 番目 mod 件数) 番目の画像を使う（仮の写真。あとで差し替える）。"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def photo_dir() -> Path:
    return Path(os.environ.get("CV_PHOTO_DIR") or ROOT / "data" / "photos")


def listing() -> list:
    try:
        return json.loads((photo_dir() / "photos.json").read_text(encoding="utf-8"))["photos"]
    except Exception:
        return []


def cards() -> list:
    """診察券（受付の画面）の画像。裏面の2枚。"""
    try:
        return json.loads((photo_dir() / "photos.json").read_text(encoding="utf-8")).get("cards", [])
    except Exception:
        return []


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
