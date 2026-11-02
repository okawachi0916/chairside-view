"""G11: ボタン3 (隠す・戻す・次の患者様へ)。"""
import json
import time

import pytest

from app.views import data as D
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401

KEYS = json.loads((ROOT / "config" / "keys.json").read_text(encoding="utf-8"))
KEY3 = KEYS["button3"].replace("Ctrl", "Control")
ROWS = [r for r in D.today_list() if r["patient_id"] == 1]
H_DOC = ROWS[0]["id"]
SECRETS = ["見本 花子", "ペニシリン", "ビスホスホネート", "根管", "白板症", "高血圧", "長く口を開けている"]


def band_visible(pg):
    return pg.locator("#band").is_visible()


@pytest.fixture()
def pg(server, browser):  # noqa: F811
    p = open_page(browser, server, f"/unit?appt={H_DOC}&role=doctor")
    p.wait_for_selector('[data-part="important"]')
    p.wait_for_function("window.VoiceKeys && document.getElementById('band')")
    time.sleep(0.5)  # キーの設定を読み終える
    yield p
    p.close()


def test_single_press_shows_band_only(pg):
    pg.keyboard.press(KEY3)
    pg.wait_for_selector("#band", state="visible", timeout=2000)
    assert "もう一度【隠】を押したら画面を隠します" in pg.inner_text("#band")
    assert "見本 花子" in pg.inner_text("body")
    assert pg.locator('[data-part="hidden-screen"]').count() == 0


def test_quick_double_press_hides_without_band(pg):
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="hidden-screen"]', timeout=2000)
    assert not band_visible(pg)
    text = pg.inner_text("body")
    assert "カルテ番号 0123 様に戻る場合は、ボタン3を2回押してください" in text
    assert "予約一覧から選ぶ" in text
    for w in SECRETS:
        assert w not in text, w
    # 画面の部品そのものが外れている
    assert pg.locator('[data-part="important"]').count() == 0
    assert pg.evaluate("document.documentElement.outerHTML.includes('見本 花子')") is False


def test_slow_double_press_via_band_hides_and_restores(pg):
    pg.keyboard.press(KEY3)
    pg.wait_for_selector("#band", state="visible", timeout=2000)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="hidden-screen"]', timeout=2000)
    assert not band_visible(pg)
    # 隠している間の帯の文
    pg.keyboard.press(KEY3)
    pg.wait_for_selector("#band", state="visible", timeout=2000)
    assert "もう一度【隠】を押したら画面を戻します" in pg.inner_text("#band")
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="important"]', timeout=2000)
    text = pg.inner_text("body")
    assert "見本 花子" in text and pg.locator('[data-part="hidden-screen"]').count() == 0


def test_restore_keeps_scroll_and_view_state(pg):
    pg.evaluate("""() => { const n = document.createElement('div'); n.id = 'scr';
                    n.style.cssText = 'position:fixed;top:300px;left:0;width:100px;height:50px;overflow:auto';
                    n.innerHTML = '<div style="height:400px">x</div>';
                    document.getElementById('view').appendChild(n); n.scrollTop = 40; }""")
    assert pg.evaluate("document.getElementById('scr').scrollTop") == 40
    pg.evaluate("document.querySelector('[data-part=intraoral-photos]').classList.add('marked')")
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="hidden-screen"]')
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('#scr')
    assert pg.evaluate("document.getElementById('scr').scrollTop") == 40
    assert pg.evaluate("document.querySelector('[data-part=intraoral-photos]').classList.contains('marked')")


def test_works_with_cursor_in_input(pg):
    pg.evaluate("""() => { const i = document.createElement('input'); i.id = 'memo-box';
                    document.body.appendChild(i); i.focus(); }""")
    assert pg.evaluate("document.activeElement.id") == "memo-box"
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="hidden-screen"]', timeout=2000)


def test_pick_patient_clears_and_goes_to_list(pg, server):  # noqa: F811
    pg.evaluate("sessionStorage.setItem('tmp', 'x')")
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="hidden-screen"]')
    pg.locator("text=予約一覧から選ぶ").click()
    pg.wait_for_url(f"http://127.0.0.1:{server}/")
    assert pg.locator("tr.row").count() == 6
    text = pg.inner_text("body")
    assert "見本 花子" not in text and "ペニシリン" not in text
    assert pg.evaluate("sessionStorage.length") == 0
    # 次の患者様の画面にも前の人は残らない
    pg.locator("tr.row").nth(1).click()
    pg.wait_for_selector('[data-part="important"]')
    assert "見本 花子" not in pg.inner_text("body")


def test_open_other_patient_while_hidden_resets(pg):
    other = D.today_list()[1]["id"]
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="hidden-screen"]')
    pg.evaluate(f"cv.openUnit({other}, 'hygienist')")
    pg.wait_for_selector('[data-part="important"]')
    text = pg.inner_text("body")
    assert "見本 一郎" in text and "見本 花子" not in text
    assert pg.locator('[data-part="hidden-screen"]').count() == 0
    # 隠していない状態でボタン3を2回 → 新しい人を隠す
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="hidden-screen"]')
    assert "カルテ番号 0456 様" in pg.inner_text("body")


def test_response_arriving_while_hidden_is_dropped(server, browser):  # noqa: F811
    p = open_page(browser, server, f"/unit?appt={H_DOC}&role=doctor")
    p.wait_for_selector('[data-part="important"]')
    time.sleep(0.5)
    held = []
    p.route("**/api/view/unit?appt=*&role=hygienist", lambda route: held.append(route))
    p.evaluate(f"cv.chart = '0123'; document.querySelector('[data-action=change-role]').click()")
    p.wait_for_timeout(300)
    assert held
    p.keyboard.press(KEY3)
    time.sleep(0.15)
    p.keyboard.press(KEY3)
    p.wait_for_selector('[data-part="hidden-screen"]')
    held[0].continue_()
    p.wait_for_timeout(800)
    assert p.locator('[data-part="hidden-screen"]').count() == 1
    assert "見本 花子" not in p.inner_text("body")
    p.close()


def test_reception_has_no_key_handling(server, browser):  # noqa: F811
    p = open_page(browser, server, "/reception?patient=1")
    p.wait_for_selector('[data-part="important"]')
    time.sleep(0.5)
    p.keyboard.press(KEY3)
    time.sleep(0.15)
    p.keyboard.press(KEY3)
    p.wait_for_timeout(500)
    assert "見本 花子" in p.inner_text("body")
    p.close()
