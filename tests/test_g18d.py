"""G18d: 写真19枚を「見本」入りの実写風に入れ直す。札が画面で切れない・全部入っている・seed と戻す道具で変わらない。"""
import os
import sqlite3
import subprocess
import sys
import hashlib

from PIL import Image

from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401
from tests.test_g18 import UNIT

PHOTOS = ROOT / "data" / "photos"
HASH = {
 "card1.jpg": "08cad6664b15e0ffb7cdb1d9deb4b8cd38c5209c654ba23a44e713aeea5dea2a",
 "card2.jpg": "ad1a12172d86a031d33d9f8e76390e4ed8d110975c613f1324a52a0602621f86",
 "photo01.jpg": "12fa1fc26da4ad9105b5d4a38d7b451d5404f9dee7d335df8b1948f81e340f30",
 "photo02.jpg": "179ad6175c43fc5d40e03ff8cd081149085c2cd2823bcd48eaa0bbae8d1e9744",
 "photo03.jpg": "a54254e9fb5978e738abb9bb1e15f6a3ee3451891812a3a286f544e9d4890fc1",
 "photo04.jpg": "02f8fc02beca8bf87618c2a451123625c3bf13d0819e03c8ca87cfd4c7af1521",
 "photo05.jpg": "1c61de65a666edf8a1160c0a05c9c1736ed459cbc7a30ac02e2b183558d6dd25",
 "photo06.jpg": "f1e9ecbfde234a4d3143bc6a757ce138ec6139c004f149e31f1d63d85a145480",
 "photo07.jpg": "912251014934933cbc7c8f9ec6456074c5a130b9d8c200d206903fd41b7f0d44",
 "photo08.jpg": "d601ae9e0b553be61edf8d44d42c272105dd5ec3fac0b68b29c1a8a77655daad",
 "photo09.jpg": "b985b73e143d348ed52bd09be3a22999cfe167ef7b8653bff0a0b84c69fc0be2",
 "photo10.jpg": "89a2e57147dca2d2d9fbf2d1cf8b17c601a72e4470e6eb48f4e27dce4edd4a04",
 "photo11.jpg": "43b47412d3ab949642d0a6448e4dad577bf355f0049d52b9d834ab85e37a1b4f",
 "photo12.jpg": "0c979fb35796c6f300c976cfd8a2dc53a508fb7612a2e221cc97c75bcbbad7ef",
 "photo13.jpg": "126f2541e7f5b57895e50202854b100cb808751ec3f0af3ea659f557e0d66a64",
 "photo14.jpg": "5f519078c94180217c834982ab8e1aa535704138381bb75974c9edb215aaea25",
 "photo15.jpg": "b6c7b183d6e57f7e665a7af5b02e45bfddbec2e2978a896a57c47c3096029367",
 "photo16.jpg": "70a89bf8d29978f36d5834bb3a3f9cb63d0e7263f57f28b875761038638ea33d",
 "photo17.jpg": "7f888ca9827cc7d5e6a6587cfdfa3f41c577dce7434aa7c9be227296e3664e36",
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_all_19_files_are_the_sample_stamped_ones_and_not_cropped():
    assert {f.name: sha(f) for f in PHOTOS.glob("*.jpg")} == HASH
    for f in PHOTOS.glob("*.jpg"):
        with Image.open(f) as im:
            assert max(im.size) <= 1600 and abs(im.size[0] / im.size[1] - 4 / 3) < 0.01, f  # 4:3 のまま（切り抜いていない）
            assert len(im.getexif()) == 0


def test_stamp_corner_not_cut_on_screen(server, browser):  # noqa: F811
    """画面の枠が4:3なので、cover でも右下の札が切れない。一覧の1枚と拡大の1枚で枠の縦横比を確かめる。"""
    pg = open_page(browser, server, UNIT)
    pg.wait_for_selector('[data-part="intraoral-photos"] .ph img')
    ph = pg.locator('[data-part="intraoral-photos"] .ph').first.bounding_box()
    assert abs(ph["width"] / ph["height"] - 4 / 3) < 0.04
    pg.wait_for_function("!!(window.cvTyped)")
    pg.click('[data-part="intraoral-photos"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    pg.evaluate("window.cvTyped('7番を拡大して')")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 1")
    assert pg.evaluate("document.querySelector('.fs-fig img').getAttribute('src')") == "/photo-files/photo07.jpg"
    big = pg.locator(".fs-fig img").bounding_box()
    assert abs(big["width"] / big["height"] - 4 / 3) < 0.04
    pg.close()


def test_reception_card_images_are_the_stamped_ones(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/reception?patient=1")
    pg.wait_for_selector(".card-imgs img")
    srcs = pg.evaluate("Array.from(document.querySelectorAll('.card-imgs img')).map(i => i.getAttribute('src'))")
    assert srcs == ["/photo-files/card1.jpg", "/photo-files/card2.jpg"]
    pg.close()


def test_seed_and_reset_keep_the_19_files(tmp_path):
    env = {**os.environ, "CV_DATA_DIR": str(tmp_path / "d"), "CV_DEMO_DIR": str(tmp_path / "demo"), "PYTHONIOENCODING": "utf-8"}
    for script in ("seed.py", "reset_for_shoot.py"):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr
        c = sqlite3.connect(tmp_path / "d" / "app.db")
        assert [n for (n,) in c.execute("SELECT number FROM photos WHERE patient_id = 1 ORDER BY number")] == list(range(1, 18))
        c.close()
        assert {f.name: sha(f) for f in PHOTOS.glob("*.jpg")} == HASH
