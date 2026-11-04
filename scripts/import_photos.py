"""撮った写真を data/photos へ入れる。位置情報などの付いた情報は全部消し、長い辺を1600pxまでにそろえる。
ファイル名の先頭の番号の順に、「診察券の裏面」を含む名前は診察券（card1.jpg、card2.jpg）へ、ほかは photo01.jpg… へ入れ、
一覧 data/photos/photos.json を書き直す。何回動かしても同じ結果になる。
使い方: python scripts/import_photos.py [写真の場所]（場所は環境変数 CV_PHOTOS_IN でも渡せる。既定は C:\\hackathon\\photos_in）"""
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "photos"
LONG_SIDE = 1600
CARD_WORD = "診察券"
NOTE = ("患者様の中の番号 n の写真は、この一覧の ((n-1) 番目 mod 件数) 番目を使う。"
        "画像と file を書き換えれば差し替えられる。診察券（受付の画面）は cards の2枚。")


def clean(src: Path, dest: Path):
    """向きを直し、長い辺を LONG_SIDE までにして、情報なしで JPEG に書く。"""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        w, h = im.size
        k = min(1.0, LONG_SIDE / max(w, h))
        if k < 1.0:
            im = im.resize((round(w * k), round(h * k)), Image.LANCZOS)
        im.save(dest, "JPEG", quality=88, optimize=True)  # exif・icc・xmp は渡さない＝残らない


def title_of(stem: str) -> str:
    return re.sub(r"^\d+[_＿\s]*", "", stem).replace("_", " ")


def main(src_dir: Path):
    files = sorted((p for p in src_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png") and re.match(r"\d+", p.name)),
                   key=lambda p: int(re.match(r"\d+", p.name).group()))
    if not files:
        raise SystemExit(f"{src_dir} に写真がありません")
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.iterdir():  # 前に入れた物・仮の絵を片づける（一覧は書き直す）
        if old.suffix.lower() in (".png", ".jpg") and (old.name.startswith(("photo", "card"))):
            old.unlink()
    photos, cards = [], []
    for p in files:
        if CARD_WORD in p.name:
            name = f"card{len(cards) + 1}.jpg"
            clean(p, OUT / name)
            cards.append({"file": name, "title": f"診察券 裏面 {len(cards) + 1}"})
        else:
            name = f"photo{len(photos) + 1:02d}.jpg"
            clean(p, OUT / name)
            photos.append({"file": name, "title": title_of(p.stem)})
    (OUT / "photos.json").write_text(json.dumps({"note": NOTE, "photos": photos, "cards": cards}, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    print(f"写真 {len(photos)} 枚、診察券 {len(cards)} 枚を {OUT} へ入れました")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CV_PHOTOS_IN") or r"C:\hackathon\photos_in"))
