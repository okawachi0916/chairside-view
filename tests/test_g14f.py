"""G14f: 実物のボタンが信号を順に送っても同時押しと分かる／ボタンの信号の記録。Claude は使わない。"""
import json
from pathlib import Path

import pytest

from app.views import data as D
from tests.screen_helper import browser, open_page, server  # noqa: F401

H_DOC = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]
DOC = f"/unit?appt={H_DOC}&role=doctor&typed=1&hide=1"
ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "keys.json").read_text(encoding="utf-8"))
LOG = ROOT / "data" / "runtime" / "logs" / "voice_timing.log"


def key(pg, kind, button):
    name = CFG[f"button{button}"]
    pg.evaluate("""([kind, code, ctrl, shift]) => window.dispatchEvent(new KeyboardEvent(kind,
        {code, key: code, ctrlKey: ctrl, shiftKey: shift, bubbles: true, cancelable: true}))""",
                [kind, name.split("+")[-1], "Ctrl" in name, "Shift" in name])


@pytest.fixture
def pg(server, browser):  # noqa: F811
    p = open_page(browser, server, DOC)
    p.wait_for_selector('[data-part="important"]')
    p.wait_for_function("!!(window.cvTyped && window.CVActions)")
    p.wait_for_function("document.body.dataset.numbersReady")
    p.wait_for_timeout(500)
    p.evaluate("""() => { window.__ran = []; const r = window.CVActions.run;
        window.CVActions.run = (n, a) => { window.__ran.push(n); return r(n, a); }; }""")
    p.click('[data-part="treatment-history"] [data-action="fullscreen"]')
    p.wait_for_selector(".fs-panel")
    yield p
    p.close()


def ran(pg):
    return pg.evaluate("window.__ran")


def band_hidden(pg):
    return pg.evaluate("document.getElementById('band').hidden")


def went_back(pg):
    pg.wait_for_function("!document.querySelector('.fs-panel')", timeout=5000)
    assert "combo-back" in ran(pg)


def test_second_key_after_slow_signal_while_first_is_held(pg):
    """実物: 1つ目を押したまま、2つ目が combo_ms より遅れて届く（帯がもう出ている）。"""
    key(pg, "keydown", 1)
    pg.wait_for_timeout(CFG["quick_press_ms"] + 300)  # 帯が出る
    assert band_hidden(pg) is False
    key(pg, "keydown", 2)
    went_back(pg)
    assert band_hidden(pg) is True
    assert "button1" not in ran(pg) and "button2" not in ran(pg)


def test_second_key_slow_but_first_not_released_even_by_a_second(pg):
    key(pg, "keydown", 2)
    pg.wait_for_timeout(1000)
    key(pg, "keydown", 1)
    went_back(pg)


def test_second_key_after_first_released_within_combo_ms(pg):
    key(pg, "keydown", 1)
    pg.wait_for_timeout(60)
    key(pg, "keyup", 1)  # 離しても、300ミリ秒以内なら同時押し
    pg.wait_for_timeout(100)
    key(pg, "keydown", 2)
    went_back(pg)


def test_second_key_after_first_released_and_too_late_is_not_combo(pg):
    key(pg, "keydown", 1)
    pg.wait_for_timeout(60)
    key(pg, "keyup", 1)
    pg.wait_for_timeout(CFG["combo_ms"] + 150)  # 離して、300ミリ秒を過ぎた
    key(pg, "keydown", 2)
    pg.wait_for_timeout(300)
    assert pg.locator(".fs-panel").count() == 1
    assert "combo-back" not in ran(pg)


def test_button3_never_combos(pg):
    key(pg, "keydown", 3)
    key(pg, "keydown", 1)  # ボタン3を押したまま: 組み合わせにならない
    pg.wait_for_timeout(300)
    assert "combo-back" not in ran(pg)
    key(pg, "keyup", 3)
    key(pg, "keyup", 1)
    pg.wait_for_timeout(CFG["quick_press_ms"] + 300)
    key(pg, "keydown", 2)
    key(pg, "keydown", 3)  # ボタン2を押したまま
    pg.wait_for_timeout(300)
    assert "combo-back" not in ran(pg)


def test_combo_hides_band_and_starts_nothing(pg):
    key(pg, "keydown", 2)
    pg.wait_for_timeout(CFG["quick_press_ms"] + 300)
    assert band_hidden(pg) is False
    key(pg, "keydown", 1)
    went_back(pg)
    pg.wait_for_timeout(300)
    assert band_hidden(pg) is True
    assert pg.evaluate("!!document.getElementById('num-band') || !!document.getElementById('num-dim')") is False
    assert pg.evaluate("!!(window.CVActive && window.CVActive[2] && window.CVActive[2]())") is False
    assert "button1" not in ran(pg) and "button2" not in ran(pg)


def test_button2_twice_still_acts(pg):
    key(pg, "keydown", 2)
    key(pg, "keyup", 2)
    pg.wait_for_timeout(120)
    key(pg, "keydown", 2)
    key(pg, "keyup", 2)
    pg.wait_for_timeout(200)
    assert "button2" in ran(pg) and "combo-back" not in ran(pg)


def test_button1_twice_still_acts(pg):
    key(pg, "keydown", 1)
    key(pg, "keyup", 1)
    pg.wait_for_timeout(120)
    with pg.expect_navigation(timeout=5000):  # 親の画面が無いので、/app の中で録音を始める（今までどおり）
        key(pg, "keydown", 1)
    assert "/app" in pg.url


def test_button2_twice_with_band_still_acts(pg):
    key(pg, "keydown", 2)
    key(pg, "keyup", 2)
    pg.wait_for_timeout(CFG["quick_press_ms"] + 300)
    assert band_hidden(pg) is False
    key(pg, "keydown", 2)
    key(pg, "keyup", 2)
    pg.wait_for_timeout(200)
    assert "button2" in ran(pg) and "combo-back" not in ran(pg)


def test_button3_twice_hides(pg):
    key(pg, "keydown", 3)
    key(pg, "keyup", 3)
    pg.wait_for_timeout(100)
    key(pg, "keydown", 3)
    key(pg, "keyup", 3)
    pg.wait_for_function("window.CVActions.isHidden()")


def test_key_signals_are_logged_with_time_and_repeat(pg):
    n = len(LOG.read_text(encoding="utf-8").splitlines()) if LOG.exists() else 0
    key(pg, "keydown", 1)
    pg.wait_for_timeout(30)
    key(pg, "keyup", 1)
    pg.evaluate("""([code, ctrl, shift]) => window.dispatchEvent(new KeyboardEvent('keydown',
        {code, key: code, ctrlKey: ctrl, shiftKey: shift, repeat: true, bubbles: true, cancelable: true}))""",
                ["F7", True, True])  # ボタン2の押しっぱなし
    for _ in range(30):
        lines = LOG.read_text(encoding="utf-8").splitlines()[n:] if LOG.exists() else []
        if len([x for x in lines if "ボタンの信号" in x]) >= 3:
            break
        pg.wait_for_timeout(100)
    sig = [x for x in lines if "ボタンの信号" in x]
    assert len(sig) == 3, sig
    assert "押した ボタン1" in sig[0] and "repeat=いいえ" in sig[0] and "t=" in sig[0]
    assert "離した ボタン1" in sig[1]
    assert "押した ボタン2" in sig[2] and "repeat=はい" in sig[2]
    assert sig[0].split()[1].count(".") == 1  # ミリ秒つき


def test_keylog_ignores_other_keys(pg):
    n = len(LOG.read_text(encoding="utf-8").splitlines()) if LOG.exists() else 0
    pg.evaluate("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyA', key: 'a', bubbles: true}))")
    pg.wait_for_timeout(300)
    lines = LOG.read_text(encoding="utf-8").splitlines()[n:] if LOG.exists() else []
    assert not [x for x in lines if "ボタンの信号" in x]
