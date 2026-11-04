"""G18: 撮った写真を番号付きで入れる。位置情報が残らない・長い辺1600px以内・「3番を拡大して」で正しい写真・seed で変わらない。"""
import json
import os
import subprocess
import sys
import urllib.request

from PIL import Image

from app.views import data as D
from app.views import photos as P
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401

PHOTOS = ROOT / "data" / "photos"
APPT = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]
UNIT = f"/unit?appt={APPT}&role=doctor&typed=1&hide=1"
LISTING = json.loads((PHOTOS / "photos.json").read_text(encoding="utf-8"))
FILES = [x["file"] for x in LISTING["photos"]] + [x["file"] for x in LISTING["cards"]]


def test_seventeen_photos_and_two_cards():
    assert [x["file"] for x in LISTING["photos"]] == [f"photo{i:02d}.jpg" for i in range(1, 18)]
    assert [x["file"] for x in LISTING["cards"]] == ["card1.jpg", "card2.jpg"]
    assert LISTING["photos"][2]["title"] == "口の中 左側"  # 3番
    assert LISTING["photos"][15]["title"] == "頬の腫れ" and LISTING["photos"][16]["title"] == "唇の腫れ"  # 18・19番のファイル


def test_no_location_or_exif_left_and_size_within_1600():
    for f in FILES:
        raw = (PHOTOS / f).read_bytes()
        for tag in (b"Exif", b"GPS", b"ns.adobe.com", b"MakerNote"):
            assert tag not in raw, (f, tag)
        with Image.open(PHOTOS / f) as im:
            assert max(im.size) <= 1600, f
            assert len(im.getexif()) == 0 and not im.getexif().get_ifd(0x8825), f
            assert not {k for k in im.info if k in ("exif", "xmp", "icc_profile")}, f


def test_import_script_strips_location_from_a_dirty_photo(tmp_path):
    """位置情報つきの大きな写真を作って通し、残らず縮むこと。"""
    src, out = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    im = Image.new("RGB", (3200, 2400), (180, 90, 90))
    ex = Image.Exif()
    ex[0x010F] = "TestMaker"
    ex.get_ifd(0x8825)[1] = "N"  # GPS の枠
    ex.get_ifd(0x8825)[2] = (35.0, 40.0, 0.0)
    im.save(src / "01_口の中_試験.jpg", exif=ex.tobytes())
    im.save(src / "02_診察券の裏面_1.jpg", exif=ex.tobytes())
    assert b"GPS" in (src / "01_口の中_試験.jpg").read_bytes() or Image.open(src / "01_口の中_試験.jpg").getexif().get_ifd(0x8825)
    code = ("import sys, pathlib; sys.path.insert(0, %r); import importlib.util as u;"
            "s = u.spec_from_file_location('imp', %r); m = u.module_from_spec(s); s.loader.exec_module(m);"
            "m.OUT = pathlib.Path(%r); m.main(pathlib.Path(%r))" % (str(ROOT), str(ROOT / "scripts" / "import_photos.py"), str(out), str(src)))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    for f in ("photo01.jpg", "card1.jpg"):
        with Image.open(out / f) as o:
            assert max(o.size) == 1600
            assert len(o.getexif()) == 0
        assert b"TestMaker" not in (out / f).read_bytes() and b"GPS" not in (out / f).read_bytes()


def test_third_photo_zoom_shows_the_right_picture(server, browser):  # noqa: F811
    pg = open_page(browser, server, UNIT)
    pg.wait_for_function("!!(window.cvNumbers && window.cvTyped && document.body.dataset.numbersReady)")
    pg.click('[data-part="intraoral-photos"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    assert pg.locator('[data-fs-panel="intraoral-photos"] .ph').count() >= 17 or pg.locator(".fs-photos .ph, .fs-photos [data-n]").count() >= 17
    nums = pg.evaluate("Array.from(document.querySelectorAll('[data-fs-panel=\"intraoral-photos\"] [data-n]')).map(e => Number(e.dataset.n))")
    assert set(range(1, 18)) <= set(nums)
    pg.evaluate("window.cvTyped('3番を拡大して')")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 1")
    src = pg.evaluate("document.querySelector('.fs-fig img').getAttribute('src')")
    assert src == "/photo-files/photo03.jpg"
    assert pg.evaluate("document.querySelector('.fs-fig img').complete && document.querySelector('.fs-fig img').naturalWidth") == 1600
    assert (PHOTOS / "photo03.jpg").read_bytes() == urllib.request.urlopen(f"http://127.0.0.1:{server}{src}").read()
    pg.evaluate("window.cvTyped('17番を拡大して')")
    pg.wait_for_function("document.querySelector('.fs-fig img') && document.querySelector('.fs-fig img').getAttribute('src').endsWith('photo17.jpg')")
    pg.close()


def test_normal_screen_shows_numbers_1_to_17(server, browser):  # noqa: F811
    pg = open_page(browser, server, UNIT)
    pg.wait_for_selector('[data-part="intraoral-photos"]')
    nos = pg.locator('[data-part="intraoral-photos"] .ph .no').all_inner_texts()
    assert sorted(int(n) for n in nos) == list(range(1, 18))
    pg.close()


def test_reception_shows_both_card_backs(server, browser):  # noqa: F811
    pg = open_page(browser, server, f"/reception?patient=1")
    pg.wait_for_selector(".card-imgs img")
    pg.wait_for_function("Array.from(document.querySelectorAll('.card-imgs img')).every(i => i.complete && i.naturalWidth > 0)")
    srcs = pg.evaluate("Array.from(document.querySelectorAll('.card-imgs img')).map(i => i.getAttribute('src'))")
    assert srcs == ["/photo-files/card1.jpg", "/photo-files/card2.jpg"]
    pg.close()


def test_seed_does_not_change_photos_or_numbers(tmp_path):
    """seed.py を2回動かしても、写真の画像・一覧と番号は変わらない。"""
    before = {f: (PHOTOS / f).read_bytes() for f in FILES + ["photos.json"]}
    env = {**os.environ, "CV_DATA_DIR": str(tmp_path)}
    nums = []
    for _ in range(2):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], capture_output=True, text=True, encoding="utf-8", errors="replace", env={**env, "PYTHONIOENCODING": "utf-8"})
        assert r.returncode == 0, r.stderr
        import sqlite3
        c = sqlite3.connect(tmp_path / "app.db")
        nums.append(c.execute("SELECT number, taken_on FROM photos WHERE patient_id = 1 ORDER BY number").fetchall())
        c.close()
    assert nums[0] == nums[1] and [n for n, _ in nums[0]] == list(range(1, 18))
    assert before == {f: (PHOTOS / f).read_bytes() for f in FILES + ["photos.json"]}
