"""G14i: 動いているものは1回押しで止まる／QR の画面を手袋のまま閉じる。Claude は使わない（偽マイク、文字起こしの結果は見ない）。"""
import json
from pathlib import Path

import pytest

from app.views import data as D
from tests.screen_helper import server  # noqa: F401
from tests.test_phone import clean, mobile  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "keys.json").read_text(encoding="utf-8"))
APPT = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]
UNIT = f"/unit?appt={APPT}&role=doctor&typed=1&hide=1"


def key(pg, kind, button):
    name = CFG[f"button{button}"]
    pg.evaluate("""([kind, code, ctrl, shift]) => window.dispatchEvent(new KeyboardEvent(kind,
        {code, key: code, ctrlKey: ctrl, shiftKey: shift, bubbles: true, cancelable: true}))""",
                [kind, name.split("+")[-1], "Ctrl" in name, "Shift" in name])


def tap(pg, button):
    key(pg, "keydown", button)
    key(pg, "keyup", button)


def double(pg, button):
    tap(pg, button)
    pg.wait_for_timeout(100)
    tap(pg, button)


@pytest.fixture
def mic_pg(server):  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        ctx = b.new_context(viewport={"width": 1920, "height": 1030})
        ctx.grant_permissions(["microphone"], origin=f"http://127.0.0.1:{server}")
        yield ctx, server
        b.close()


def listening(pg):
    pg.wait_for_selector(".topbar .mic.rec")
    pg.wait_for_selector(".num-badge")


def stopped(pg):
    pg.wait_for_function("!document.querySelector('.topbar .mic.rec') && !document.querySelector('.num-badge')", timeout=5000)


def test_button2_one_press_stops_listening_in_unit(mic_pg):
    ctx, port = mic_pg
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{port}{UNIT.replace('&typed=1&hide=1', '')}")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("window.VoiceKeys && document.getElementById('band')")
    pg.wait_for_timeout(500)
    double(pg, 2)
    listening(pg)
    tap(pg, 2)  # 6秒を待たず、1回で止まる
    stopped(pg)


def test_button2_one_press_stops_listening_from_parent_frame(mic_pg):
    """/app（録音の親）にフォーカスがあるときも、声の受付は1回で止まる。"""
    ctx, port = mic_pg
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{port}/app?go=" + f"/unit?appt={APPT}%26role=doctor")
    inner = pg.frame_locator("iframe").locator('[data-part="important"]')
    inner.wait_for(timeout=15000)
    pg.wait_for_function("window.VoiceKeys && document.getElementById('band')")
    pg.wait_for_timeout(500)
    double(pg, 2)  # 親のキー
    fr = [f for f in pg.frames if f != pg.main_frame][0]
    fr.wait_for_selector(".topbar .mic.rec")
    fr.wait_for_selector(".num-badge")
    tap(pg, 2)
    fr.wait_for_function("!document.querySelector('.topbar .mic.rec') && !document.querySelector('.num-badge')", timeout=5000)


def open_qr(pg):
    pg.click('[data-part="intraoral-photos"] [data-action="fullscreen"]')
    pg.wait_for_selector(".fs-panel")
    pg.click('.fs-panel [data-action="phone"]')
    pg.wait_for_selector("#phone-modal .qr svg")


@pytest.fixture
def qr(server, mobile):  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1920, "height": 1030})
        pg.goto(f"http://127.0.0.1:{server}{UNIT}")
        pg.wait_for_selector('[data-part="important"]')
        pg.wait_for_function("!!(window.cvTyped && window.CVActions && window.VoiceKeys)")
        pg.wait_for_function("document.body.dataset.numbersReady")
        pg.wait_for_timeout(500)
        open_qr(pg)
        yield pg
        b.close()


def modal(pg):
    return pg.locator("#phone-modal").count()


def back_to_photos(pg):
    pg.wait_for_function("!document.getElementById('phone-modal')", timeout=5000)
    assert pg.locator('.fs-panel[data-fs-panel="intraoral-photos"]').count() == 1  # QR を開く前の画面


def test_qr_closes_with_button_1_and_2_together(qr):
    key(qr, "keydown", 1)
    key(qr, "keydown", 2)
    key(qr, "keyup", 1)
    key(qr, "keyup", 2)
    back_to_photos(qr)


@pytest.mark.parametrize("word", ["戻して", "閉じて", "閉じる"])
def test_qr_closes_with_voice_word(qr, word):
    qr.evaluate("w => window.cvTyped(w)", word)
    back_to_photos(qr)


def test_back_does_not_count_qr_as_a_step(qr):
    """QR を閉じたあとの「戻して」は、QR の分を戻らず、全画面を閉じる。"""
    qr.evaluate("window.cvTyped('戻して')")
    back_to_photos(qr)
    qr.evaluate("window.cvTyped('戻して')")
    qr.wait_for_function("!document.querySelector('.fs-panel')", timeout=5000)


def test_button3_closes_qr_then_hides(qr):
    double(qr, 3)
    qr.wait_for_selector(".hide-panel")
    assert modal(qr) == 0
    double(qr, 3)  # 戻す
    qr.wait_for_selector(".hide-panel", state="detached")
    assert modal(qr) == 0
