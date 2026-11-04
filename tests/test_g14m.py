"""G14m: 「口腔内写真」を「写真」に改める。画面に出ない・声は新旧どちらも通る・「写真」は短いので取り違えない。"""
import subprocess

import pytest

from app.views import data as D
from app.voice.interpret import interpret
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401

OLD = "口腔内写真"
APPT = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]
UNIT = f"/unit?appt={APPT}&role=doctor&typed=1&hide=1"


def test_old_name_is_gone_from_the_program_and_settings_except_the_voice_table():
    out = subprocess.run(["git", "grep", "-l", OLD, "--", "app", "config", "README.md"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.split()
    assert out == ["config/commands.json"], out  # 言い慣れた言い方を通す所だけ
    for line in (ROOT / "config" / "commands.json").read_text(encoding="utf-8").splitlines():
        if OLD in line:
            assert line.strip().startswith('"言葉": "(口腔内写真|写真)の{n') or "(口腔内|)写真" in line, line  # 正規表現の中だけ


@pytest.mark.parametrize("role", ["doctor", "hygienist"])
def test_no_old_name_on_screens(server, browser, role):  # noqa: F811
    pg = open_page(browser, server, f"/unit?appt={APPT}&role={role}&typed=1&hide=1")
    pg.wait_for_function("!!(window.cvNumbers && document.body.dataset.numbersReady)")
    assert OLD not in pg.content()
    assert "写真" in pg.inner_text('[data-part="intraoral-photos"]')
    pg.click('[data-part="intraoral-photos"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    assert OLD not in pg.content()
    assert "写真" in pg.inner_text(".fs-panel")
    pg.evaluate("window.cvTyped('戻して')")
    pg.evaluate("window.cvNumbers(true)")
    assert OLD not in pg.content()
    pg.close()


def test_no_old_name_on_reception_and_say_list(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/reception?patient=1")
    pg.wait_for_selector(".card-imgs img")
    assert OLD not in pg.content()
    pg.close()
    pg = open_page(browser, server, UNIT)
    pg.wait_for_function("!!(window.cvNumbers && window.cvTyped && document.body.dataset.numbersReady)")
    pg.evaluate("window.cvTyped('言える言葉')")
    pg.wait_for_timeout(500)
    assert OLD not in pg.content()
    pg.close()


def _act(text):
    r = interpret(text)
    assert r["kind"] == "操作", text
    return r["action"], r.get("arg"), r.get("numbers")


@pytest.mark.parametrize("new,old", [
    ("写真を全画面にして", "口腔内写真を全画面にして"), ("写真を拡大して", "口腔内写真を拡大して"), ("写真の全画面", "口腔内写真の全画面"),
    ("写真の3番を拡大して", "口腔内写真の3番を拡大して"), ("写真の1番と3番を並べて", "口腔内写真の1番と3番を並べて"),
    ("写真の1番と3番を拡大して", "口腔内写真の1番と3番を拡大して"), ("写真の詳細を教えて", "口腔内写真の詳細を教えて"),
    ("写真を拡大してください", "口腔内写真を拡大してください"),
])
def test_new_and_old_wording_do_the_same(new, old):
    assert _act(new) == _act(old)


def test_photo_words_open_the_photo_screen():
    assert _act("写真を全画面にして") == ("fs-open", "intraoral-photos", None)
    assert _act("写真の3番を拡大して")[0] == "photo-open"


@pytest.mark.parametrize("text,action", [
    ("スマホで写真をやり取り", "phone-open"), ("スマホで写真", "phone-open"),
    ("スマホ", "phone-open"), ("スマホで画像をやり取り", "phone-open"),
])
def test_photo_exchange_words_still_open_the_qr(text, action):
    assert _act(text)[0] == action


@pytest.mark.parametrize("text", ["写真を撮りますね", "写真をやり取り", "写真をやり取りして", "写真を見てください", "写真ですね", "写真", "レントゲン写真を撮ります", "この写真はきれいですね"])
def test_short_word_photo_does_not_act_in_ordinary_talk(text):
    assert interpret(text)["kind"] != "操作", text


def test_number_18_is_the_woman_with_the_stamp(server, browser):  # noqa: F811
    import hashlib
    from tests.test_g18d import HASH
    from PIL import Image
    assert hashlib.sha256((ROOT / "data" / "photos" / "photo16.jpg").read_bytes()).hexdigest() == HASH["photo16.jpg"]
    pg = open_page(browser, server, UNIT)
    pg.wait_for_function("!!(window.cvNumbers && window.cvTyped && document.body.dataset.numbersReady)")
    pg.click('[data-part="intraoral-photos"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    pg.evaluate("window.cvTyped('写真の16番を拡大して')")
    pg.wait_for_function("document.querySelector('.fs-fig img')")
    assert pg.evaluate("document.querySelector('.fs-fig img').getAttribute('src')") == "/photo-files/photo16.jpg"
    pg.close()
    with Image.open(ROOT / "data" / "photos" / "photo16.jpg") as im:
        assert len(im.getexif()) == 0 and max(im.size) <= 1600
