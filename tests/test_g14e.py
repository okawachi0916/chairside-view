"""G14e: 声で開いた全画面とマウスで開いた全画面が同じ／質問の答えのあとも並びが動かない／ボタン1+2の同時押しで「戻して」。
Claude は使わない（質問は偽物の口）。"""
import json
import os
import time
from pathlib import Path

import pytest

from app.views import data as D
from tests.screen_helper import browser, open_page, server  # noqa: F401

H_DOC = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]
DOC = f"/unit?appt={H_DOC}&role=doctor&typed=1&hide=1"
FAKE = Path(os.environ["CHAIRSIDE_AI_FAKE_FILE"])
CFG = json.loads((Path(__file__).resolve().parent.parent / "config" / "keys.json").read_text(encoding="utf-8"))

WORDS = {
    "important": "重要事項を全画面にして", "medical-history": "全身既往を全画面にして", "today-treatment": "今日の処置を全画面にして",
    "treatment-history": "治療歴を全画面にして", "intraoral-photos": "口腔内写真を全画面にして", "spoken-summary": "話した内容を全画面にして",
}


def open_unit(browser, server, path=DOC):  # noqa: F811
    pg = open_page(browser, server, path)
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("!!(window.cvTyped && window.cvNumbers && window.CVAsk)")
    pg.wait_for_function("document.body.dataset.numbersReady")
    pg.evaluate("document.fonts.ready")
    return pg


def mouse_open(pg, part):
    pg.click(f'[data-part="{part}"] [data-action="fullscreen"]')
    pg.wait_for_selector(".fs-panel")


def panel_state(pg):
    return pg.evaluate(
        "() => { const p = document.querySelector('.fs-panel');"
        " return [p.getAttribute('data-fs-panel'), p.outerHTML, document.body.className]; }")


def close(pg):
    pg.click('.fs-panel [data-action="fs-close"]')
    pg.wait_for_function("!document.querySelector('.fs-panel')")


# ---- 1. 声で開いても、マウスで開いても同じ画面 ----

@pytest.mark.parametrize("part", list(WORDS))
def test_voice_open_equals_mouse_open(server, browser, part):  # noqa: F811
    pg = open_unit(browser, server)
    mouse_open(pg, part)
    pg.wait_for_function("Array.from(document.querySelectorAll('.fs-panel img')).every(i => i.complete)")
    m = panel_state(pg)
    shot_m = pg.locator(".fs-panel").screenshot()
    close(pg)
    pg.evaluate("w => window.cvTyped(w)", WORDS[part])
    pg.wait_for_selector(".fs-panel")
    pg.wait_for_function("Array.from(document.querySelectorAll('.fs-panel img')).every(i => i.complete)")
    pg.wait_for_timeout(300)
    assert panel_state(pg) == m
    assert pg.locator(".fs-panel").screenshot() == shot_m, "声で開いた画面とマウスで開いた画面の見た目がちがう"
    pg.close()


def test_voice_open_goes_through_the_mouse_road(server, browser):  # noqa: F811
    """声で開くときも、画面のボタンの click（view.js の fs-open）を通る。"""
    pg = open_unit(browser, server)
    pg.evaluate("""() => { window.__clicks = [];
      document.addEventListener('click', e => { const a = e.target.closest('[data-action=fullscreen]');
        if (a) window.__clicks.push(a.closest('[data-part]').dataset.part); }, true); }""")
    pg.evaluate("w => window.cvTyped(w)", "今日の処置を全画面にして")
    pg.wait_for_selector('[data-fs-panel="today-treatment"]')
    assert pg.evaluate("window.__clicks") == ["today-treatment"]
    close(pg)
    pg.evaluate("window.cvNumbers(true)")
    pg.evaluate("window.cvTyped('1番')")  # 丸の番号
    pg.wait_for_selector('[data-fs-panel="important"]')
    assert pg.evaluate("window.__clicks") == ["today-treatment", "important"]
    pg.close()


def test_voice_open_from_inside_another_fullscreen(server, browser):  # noqa: F811
    """全画面の中から別の全画面へ声で移っても、マウスで開いた形と同じ。"""
    pg = open_unit(browser, server)
    mouse_open(pg, "treatment-history")
    pg.evaluate("w => window.cvTyped(w)", "今日の処置を全画面にして")
    pg.wait_for_selector('[data-fs-panel="today-treatment"]')
    pg.wait_for_timeout(300)
    v = panel_state(pg)
    close(pg)
    mouse_open(pg, "today-treatment")
    assert panel_state(pg) == v
    pg.close()


# ---- 2. 質問の答えのあとも、ほかの欄は動かない ----

def reply(text):
    FAKE.write_text(json.dumps({"reply": text, "delay_ms": 0}), encoding="utf-8")


@pytest.fixture
def fake_found():
    yield
    reply('{"result":"unclear"}')


def view_layout(pg):
    return pg.evaluate("() => [...document.querySelectorAll('#view > *:not(.fs-panel)')].map(e => e.outerHTML)")


def test_answer_does_not_pin_important_on_top(server, browser, fake_found):  # noqa: F811
    from app.ai.records import build_records

    with D.con() as c:
        ref = next(r.number for r in build_records(c, 1) if r.ref == "important:1")
    pg = open_unit(browser, server)
    before = view_layout(pg)
    reply(json.dumps({"result": "found", "record": ref}))
    pg.evaluate("t => window.cvTyped(t)", "ペニシリンの記録は？")
    pg.wait_for_selector('[data-fs-panel="answer"]')
    # 答えは答えの場所に出す。重要事項の帯を上に残さない
    assert not pg.locator('[data-part="important"]').is_visible()
    assert pg.locator(".ai-frame").is_visible()
    assert view_layout(pg) == before  # ほかの欄の並び・中身は動かない
    close(pg)
    assert view_layout(pg) == before
    assert pg.locator('[data-part="important"]').is_visible()
    pg.close()


@pytest.mark.parametrize("part", ["today-treatment", "treatment-history", "medical-history", "important"])
def test_any_fullscreen_opens_after_an_answer(server, browser, fake_found, part):  # noqa: F811
    from app.ai.records import build_records

    with D.con() as c:
        ref = next(r.number for r in build_records(c, 1) if r.ref == "important:1")
    pg = open_unit(browser, server)
    mouse_open(pg, "today-treatment")
    fresh = panel_state(pg)
    close(pg)
    reply(json.dumps({"result": "found", "record": ref}))
    pg.evaluate("t => window.cvTyped(t)", "ペニシリンの記録は？")
    pg.wait_for_selector('[data-fs-panel="answer"]')
    close(pg)  # もとに戻す
    mouse_open(pg, "today-treatment")
    assert panel_state(pg) == fresh
    close(pg)
    mouse_open(pg, part)  # マウスで、どの全画面も開く
    assert pg.locator(".fs-scroll").count() >= 1 and pg.locator(".fs-panel").count() == 1
    pg.close()


def test_answer_then_voice_opens_a_fullscreen(server, browser, fake_found):  # noqa: F811
    from app.ai.records import build_records

    with D.con() as c:
        ref = next(r.number for r in build_records(c, 1) if r.ref == "important:1")
    pg = open_unit(browser, server)
    mouse_open(pg, "treatment-history")
    m = panel_state(pg)
    close(pg)
    reply(json.dumps({"result": "found", "record": ref}))
    pg.evaluate("t => window.cvTyped(t)", "ペニシリンの記録は？")
    pg.wait_for_selector('[data-fs-panel="answer"]')
    pg.evaluate("w => window.cvTyped(w)", "治療歴を全画面にして")  # 答えの画面から直接
    pg.wait_for_selector('[data-fs-panel="treatment-history"]')
    assert pg.locator(".fs-panel").count() == 1
    assert panel_state(pg) == m
    pg.close()


# ---- 3. ボタン1とボタン2の同時押しで「戻して」 ----

def keydown(pg, name):
    ctrl, shift, code = "Ctrl" in name, "Shift" in name, name.split("+")[-1]
    pg.evaluate("""([code, ctrl, shift]) => window.dispatchEvent(new KeyboardEvent('keydown',
        {code, key: code, ctrlKey: ctrl, shiftKey: shift, bubbles: true, cancelable: true}))""", [code, ctrl, shift])


def combo_state(pg):
    return pg.evaluate("() => [document.getElementById('band').hidden, document.body.dataset.guide || '', !!document.body.dataset.combo]")


@pytest.fixture
def real_keys_unit(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.wait_for_function("document.getElementById('band') !== null")
    pg.wait_for_timeout(500)  # keys.json を読み終える
    yield pg
    pg.close()


def test_combo_ms_is_in_config():
    assert CFG["combo_ms"] == 300


@pytest.mark.parametrize("order", [(1, 2), (2, 1)])
def test_combo_goes_back_like_voice(real_keys_unit, order):
    pg = real_keys_unit
    mouse_open(pg, "treatment-history")
    keydown(pg, CFG[f"button{order[0]}"])
    pg.wait_for_timeout(120)
    keydown(pg, CFG[f"button{order[1]}"])
    pg.wait_for_function("!document.querySelector('.fs-panel')", timeout=5000)
    assert pg.evaluate("document.body.dataset.heard").startswith("「戻して」")
    pg.wait_for_function("document.body.dataset.combo")
    info = json.loads(pg.evaluate("document.body.dataset.combo"))
    assert (info["first"], info["second"]) == order and 0 < info["gap_ms"] <= CFG["combo_ms"]
    assert info["action"] == "fs-close"
    # 帯は出ない・暗くならない・録音も声の受付も始まらない
    pg.wait_for_timeout(CFG["quick_press_ms"] + 300)
    assert pg.evaluate("document.getElementById('band').hidden") is True
    assert pg.evaluate("document.body.dataset.guide || ''") == ""
    assert pg.evaluate("document.getElementById('num-band') === null && document.getElementById('num-dim') === null")
    assert pg.evaluate("!!(window.CVActive && window.CVActive[2] && window.CVActive[2]())") is False
    assert pg.evaluate("document.body.dataset.mic || ''") in ("", "idle")


def test_combo_writes_one_log_line(real_keys_unit, server):
    pg = real_keys_unit
    log = Path(__file__).resolve().parent.parent / "data" / "runtime" / "logs" / "voice_timing.log"
    n = len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0
    mouse_open(pg, "important")
    keydown(pg, CFG["button1"])
    pg.wait_for_timeout(80)
    keydown(pg, CFG["button2"])
    pg.wait_for_function("document.body.dataset.combo")
    for _ in range(30):
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        if len(lines) > n:
            break
        time.sleep(0.1)
    new = [x for x in lines[n:] if "ボタン同時押し" in x]
    assert len(new) == 1 and "ボタン1→ボタン2" in new[0] and "fs-close" in new[0], new


def test_single_press_still_shows_band_and_does_nothing(real_keys_unit):
    pg = real_keys_unit
    mouse_open(pg, "important")
    keydown(pg, CFG["button1"])
    pg.wait_for_timeout(CFG["quick_press_ms"] + 200)
    assert pg.evaluate("document.getElementById('band').hidden") is False  # 1回目は帯が出るだけ
    assert pg.locator(".fs-panel").count() == 1  # 何も動かない
    assert not pg.evaluate("document.body.dataset.combo")


def test_slow_second_press_is_not_a_combo(real_keys_unit):
    pg = real_keys_unit
    mouse_open(pg, "important")
    keydown(pg, CFG["button1"])
    pg.evaluate("window.dispatchEvent(new KeyboardEvent('keyup', {code: 'F6', bubbles: true}))")  # 離した
    pg.wait_for_timeout(CFG["combo_ms"] + 150)
    keydown(pg, CFG["button2"])  # 離してから300ミリ秒より後: 同時押しではない
    pg.wait_for_timeout(500)
    assert pg.locator(".fs-panel").count() == 1
    assert not pg.evaluate("document.body.dataset.combo")


def test_button3_is_not_part_of_a_combo(real_keys_unit):
    pg = real_keys_unit
    mouse_open(pg, "important")
    keydown(pg, CFG["button3"])
    pg.wait_for_timeout(60)
    keydown(pg, CFG["button1"])  # ボタン3は組み合わせに使わない
    pg.wait_for_timeout(300)
    assert not pg.evaluate("document.body.dataset.combo")
    assert pg.locator(".fs-panel").count() == 1 or pg.evaluate("window.CVActions.isHidden()")


def test_combo_outside_fullscreen_does_nothing_harmful(real_keys_unit):
    pg = real_keys_unit
    keydown(pg, CFG["button2"])
    pg.wait_for_timeout(60)
    keydown(pg, CFG["button1"])
    pg.wait_for_function("document.body.dataset.combo")
    assert pg.locator(".fs-panel").count() == 0
    assert pg.evaluate("document.getElementById('band').hidden") is True
