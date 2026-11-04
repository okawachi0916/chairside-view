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
    "photo01.jpg": "12fa1fc26da4ad9105b5d4a38d7b451d5404f9dee7d335df8b1948f81e340f30",
    "photo02.jpg": "179ad6175c43fc5d40e03ff8cd081149085c2cd2823bcd48eaa0bbae8d1e9744",
    "photo03.jpg": "a54254e9fb5978e738abb9bb1e15f6a3ee3451891812a3a286f544e9d4890fc1",
    "photo04.jpg": "02f8fc02beca8bf87618c2a451123625c3bf13d0819e03c8ca87cfd4c7af1521",
    "photo05.jpg": "1c61de65a666edf8a1160c0a05c9c1736ed459cbc7a30ac02e2b183558d6dd25",
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
