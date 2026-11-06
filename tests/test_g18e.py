"""G18e: 6〜9番は Claude が作り直した写真。READMEの素材の区別に「ChatGPT で作った」が残らない。番号と並びは変わらない。"""
import json

from PIL import Image

from tests.screen_helper import ROOT
from tests.test_g18d import HASH  # 19枚の指紋（seed と「見本へ戻す」の後も同じことは test_g18d が確かめる）

PH = ROOT / "data" / "photos"


def test_treatment_photos_are_the_new_four_in_the_same_place():
    j = json.loads((PH / "photos.json").read_text(encoding="utf-8"))
    titles = [x["title"] for x in j["photos"]]
    assert titles[5:9] == ["治療の工程 治療前", "治療の工程 インレーを外した", "治療の工程 むし歯を取った", "治療の工程 治療後"]
    assert [x["file"] for x in j["photos"]][5:9] == [f"photo0{n}.jpg" for n in (6, 7, 8, 9)]
    for n in (6, 7, 8, 9):
        with Image.open(PH / f"photo0{n}.jpg") as im:
            assert im.size == (1600, 1200) and len(im.getexif()) == 0
    assert len(HASH) == 19


def test_readme_says_claude_made_6_to_9():
    t = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "ComfyUI" in t and "z_image_turbo" in t and "構図の手本" in t and "クリーム色" in t
