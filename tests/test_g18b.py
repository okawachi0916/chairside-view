"""G18b: 口の中の写真1〜5番を模型の写真に差し替え。番号・説明・並びは同じ。seed と「見本へ戻す」で変わらない。"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys

from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401
from tests.test_g18 import APPT, UNIT

PHOTOS = ROOT / "data" / "photos"
MODEL = {  # 模型の写真（G18b で入れ替えた5枚）
    "photo01.jpg": "a28c4f4e43bf04ac9c36cc7a85bb75af27c538531a99962016ba4c2f434502aa",
    "photo02.jpg": "e7e3edb6462ca2ba25120085f43c60613b0b536ca139383a6a3d944f6164371c",
    "photo03.jpg": "e9eca1bfef309f7d33ae45fe430400185de8f27ccaf4b72aeb0762761e212d6c",
    "photo04.jpg": "3dfda9e5cf6357b3f86c842f7b983009d4c7b024cfc052c6833afe0713866350",
    "photo05.jpg": "818f96dcee59586a89e7c63997f103d53b88658e3dfa6010341c7ce47c582bd3",
}


def sha(name):
    return hashlib.sha256((PHOTOS / name).read_bytes()).hexdigest()


def test_photos_1_to_5_are_the_model_pictures_and_titles_unchanged():
    assert {n: sha(n) for n in MODEL} == MODEL
    items = json.loads((PHOTOS / "photos.json").read_text(encoding="utf-8"))["photos"]
    assert [x["file"] for x in items[:5]] == list(MODEL)
    assert [x["title"] for x in items[:5]] == ["口の中 正面", "口の中 右側", "口の中 左側", "口の中 上の歯", "口の中 下の歯"]
    assert len(items) == 17


def test_second_photo_zoom_shows_right_side(server, browser):  # noqa: F811
    pg = open_page(browser, server, UNIT)
    pg.wait_for_function("!!(window.cvNumbers && window.cvTyped && document.body.dataset.numbersReady)")
    pg.click('[data-part="intraoral-photos"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    pg.evaluate("window.cvTyped('2番を拡大して')")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 1")
    src = pg.evaluate("document.querySelector('.fs-fig img').getAttribute('src')")
    assert src == "/photo-files/photo02.jpg"
    pg.close()


def test_seed_and_reset_keep_photos_and_numbers(tmp_path):
    data, demo = tmp_path / "data", tmp_path / "demo"
    env = {**os.environ, "CV_DATA_DIR": str(data), "CV_DEMO_DIR": str(demo), "PYTHONIOENCODING": "utf-8"}
    before = {f.name: f.read_bytes() for f in PHOTOS.iterdir()}
    for script in ("seed.py", "reset_for_shoot.py"):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr
        c = sqlite3.connect(data / "app.db")
        nums = [n for (n,) in c.execute("SELECT number FROM photos WHERE patient_id = 1 ORDER BY number")]
        c.close()
        assert nums == list(range(1, 18))
        assert {f.name: f.read_bytes() for f in PHOTOS.iterdir()} == before
    assert {n: sha(n) for n in MODEL} == MODEL
