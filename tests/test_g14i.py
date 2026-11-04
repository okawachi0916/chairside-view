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


# ---------- G14j: QR の画面の「閉じる」にも番号 ----------
def test_qr_close_button_gets_number_1_and_stays_bright(qr):
    assert qr.evaluate("window.cvNumbers(true)") == 1
    b = qr.locator(".num-badge")
    assert b.inner_text() == "1番" and b.get_attribute("data-key") == "modal:close"
    btn = qr.locator('#phone-modal [data-act="close"]').bounding_box()
    bb = b.bounding_box()
    assert not (bb["x"] < btn["x"] + btn["width"] and bb["x"] + bb["width"] > btn["x"] and bb["y"] < btn["y"] + btn["height"] and bb["y"] + bb["height"] > btn["y"])
    assert 0 <= btn["y"] - (bb["y"] + bb["height"]) <= 40  # 少し上
    assert qr.locator("#num-dim").count() == 1
    assert qr.locator("#num-dim").evaluate("e => e.style.clipPath").count("Z") == 2  # ボタンの所に穴
    assert qr.evaluate("window.cvNumbers(false)") == 0 and qr.locator("#num-dim").count() == 0
    assert modal(qr) == 1  # 番号を消しても QR は開いたまま


def test_qr_number_1_by_voice_closes_only_qr(qr):
    qr.evaluate("window.cvNumbers(true)")
    qr.evaluate("window.cvTyped('1番')")
    back_to_photos(qr)


def test_qr_button2_double_press_shows_numbers_and_again_hides(server, mobile):  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        ctx = b.new_context(viewport={"width": 1920, "height": 1030})
        ctx.grant_permissions(["microphone"], origin=f"http://127.0.0.1:{server}")
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{server}{UNIT.replace('&typed=1&hide=1', '')}")
        pg.wait_for_selector('[data-part="important"]')
        pg.wait_for_function("!!(window.VoiceKeys && document.body.dataset.numbersReady)")
        pg.wait_for_timeout(500)
        open_qr(pg)
        double(pg, 2)
        pg.wait_for_selector(".num-badge")
        assert pg.locator(".num-badge").inner_text() == "1番" and pg.locator("#num-dim").count() == 1
        tap(pg, 2)  # もう1回押したら番号を消す
        pg.wait_for_function("!document.querySelector('.num-badge')", timeout=5000)
        assert modal(pg) == 1
        b.close()


# ---------- G14k: ボタンが動いたら、明るい穴と札も合わせ直す ----------
def holes(pg):
    import re
    clip = pg.locator("#num-dim").evaluate("e => e.style.clipPath")
    return [tuple(int(v) for v in m) for m in re.findall(r"M\s*(-?\d+)\s+(-?\d+)\s*h\s*(\d+)\s*v\s*(\d+)", clip)]


def targets(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('.num-badge')).map(b => {
        const k = b.dataset.key;
        const el = k === 'say-list' ? document.getElementById('say-list-btn') : k === 'change-role' ? document.querySelector('[data-action=change-role]')
          : k === 'phone' ? document.querySelector('[data-action=phone]') : document.querySelector('[data-part="' + k + '"] [data-action=fullscreen]');
        const r = el.getBoundingClientRect();
        const q = b.getBoundingClientRect();
        return {key: k, r: [r.left, r.top, r.width, r.height].map(Math.round), badge: [q.left, q.top, q.right, q.bottom]};
    })""")


def assert_lit(pg):
    t = targets(pg)
    h = holes(pg)
    assert len(h) == len(t) and len(t) >= 8
    for x in t:
        assert any(all(abs(p - q) <= 1 for p, q in zip(hh, x["r"])) for hh in h), x["key"]  # 穴はボタンと同じ場所
        bl, bt, br, bb = x["badge"]
        l, tp, w, hgt = x["r"]
        assert not (bl < l + w and br > l and bt < tp + hgt and bb > tp), x["key"]  # 札はボタンに重ならない


def test_holes_follow_buttons_when_topbar_moves(mic_pg):
    ctx, port = mic_pg
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{port}{UNIT}")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("!!(window.cvNumbers && document.body.dataset.numbersReady)")
    pg.wait_for_timeout(500)
    pg.evaluate("window.cvNumbers(true)")
    assert_lit(pg)
    # 上の段の印が出入りして、ボタンの位置が動いた
    pg.evaluate("""() => { const m = document.querySelector('.topbar .mic'); m.style.minWidth = '160px'; m.style.marginRight = '40px'; }""")
    pg.wait_for_timeout(300)
    assert_lit(pg)
    pg.evaluate("document.querySelector('.topbar .mic').style.display = 'none'")
    pg.wait_for_timeout(300)
    assert_lit(pg)
    pg.set_viewport_size({"width": 1500, "height": 900})  # 窓の大きさ
    pg.wait_for_timeout(300)
    assert_lit(pg)
    pg.close()


def test_holes_match_buttons_while_listening(mic_pg):
    ctx, port = mic_pg
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{port}{UNIT}")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("window.VoiceKeys && document.body.dataset.numbersReady")
    pg.wait_for_timeout(500)
    assert pg.evaluate("window.cvNumbers(true)") >= 8  # 聞いていない間
    assert_lit(pg)
    pg.evaluate("window.cvNumbers(false)")
    double(pg, 2)  # 聞いている間
    listening(pg)
    pg.wait_for_timeout(500)
    assert_lit(pg)
    tap(pg, 2)
    stopped(pg)
