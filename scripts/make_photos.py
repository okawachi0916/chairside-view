"""仮の口腔内写真（架空の絵）を12枚作り、一覧 data/photos/photos.json を書く。
本物の写真に差し替えるときは、画像を data/photos に置いて photos.json の file を書き換える。
使い方: python scripts/make_photos.py（何回動かしても同じ絵になる）"""
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "data" / "photos"
W, H = 640, 480
TITLES = ["上顎 咬合面", "下顎 咬合面", "正面", "右側", "左側", "上顎 前歯 唇側", "下顎 前歯 唇側", "右上 臼歯",
          "左上 臼歯", "右下 臼歯", "左下 臼歯", "全顎 パノラマ風"]


def picture(i: int) -> Image.Image:
    rnd = random.Random(1000 + i)
    tint = [(200 - 6 * i, 120 + 5 * i, 130), (180, 110 + 4 * i, 120 - 3 * i)][i % 2]
    img = Image.new("RGB", (W, H), tint)
    d = ImageDraw.Draw(img)
    for y in range(H):  # 上から下へゆるい明るさの変化
        shade = int(40 * y / H)
        d.line([(0, y), (W, y)], fill=(max(0, tint[0] - shade), max(0, tint[1] - shade), max(0, tint[2] - shade)))
    n = 14 + (i % 3) * 2
    for k in range(n):  # 歯の並び（弓なりに並べた楕円）
        t = math.pi * (0.08 + 0.84 * k / (n - 1))
        x = W / 2 + math.cos(t) * 250
        y = 110 + math.sin(t) * 230 if i % 2 == 0 else 370 - math.sin(t) * 230
        w, h = 46 + rnd.randint(-5, 5), 62 + rnd.randint(-6, 6)
        tone = 238 - rnd.randint(0, 14)
        d.ellipse([x - w / 2, y - h / 2, x + w / 2, y + h / 2], fill=(tone, tone - 4, tone - 20), outline=(150, 140, 120), width=2)
    if i % 4 == 3:  # 数枚に架空の詰め物の印
        d.ellipse([W / 2 - 14, 230, W / 2 + 14, 258], fill=(120, 120, 130))
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items = []
    for i in range(12):
        name = f"photo{i + 1:02d}.png"
        picture(i).save(OUT / name, optimize=True)
        items.append({"file": name, "title": f"仮の写真 {i + 1}（{TITLES[i]}）"})
    note = "架空の絵。患者様の中の番号 n の写真は、この一覧の ((n-1) 番目 mod 件数) 番目を使う。画像と file を書き換えれば差し替えられる。"
    (OUT / "photos.json").write_text(json.dumps({"note": note, "photos": items}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
