"""G21b: 新しい版が入ったら「更新」のボタンを出す。使い回さない・全部の画面に出る・押したときだけ読み直す。"""
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from app import versioning
from app.views import data as D
from tests.screen_helper import ROOT, browser, server  # noqa: F401
from tests.test_phone import MPORT, link, mobile  # noqa: F401

ROWS = [r for r in D.today_list() if r["patient_id"] == 1]
APPT = ROWS[0]["id"]
PROBE = ROOT / "config" / "_version_probe.json"
FAST = "window.CV_POLL_MS = 300;"


@contextmanager
def new_version():
    """main に新しい版が入った状態を作る（一番新しいファイルの時刻を進める）。"""
    PROBE.write_text("{}", encoding="utf-8")
    t = time.time() + 120
    os.utime(PROBE, (t, t))
    try:
        yield
    finally:
        PROBE.unlink(missing_ok=True)


def page(browser, url, ctx=None):
    ctx = ctx or browser.new_context(viewport={"width": 1920, "height": 1030})
    ctx.add_init_script(FAST)
    pg = ctx.new_page()
    pg.goto(url)
    return pg


def test_version_endpoint_and_cache_headers(server):  # noqa: F811
    base = f"http://127.0.0.1:{server}"
    with httpx.Client(base_url=base) as h:
        v = h.get("/version").json()
        assert re.fullmatch(r"\d+", v["v"]) and re.fullmatch(r"\d\d:\d\d", v["time"])
        assert h.get("/version").headers["cache-control"] == "no-store"
        for path in ["/static/js/actions.js", "/static/css/mock.css", "/config/keys.json"]:
            assert h.get(path).headers["cache-control"] == "no-cache", path
        old = v["v"]
        with new_version():
            time.sleep(1.3)
            assert h.get("/version").json()["v"] != old  # 新しいファイルが入ると変わる
        time.sleep(1.3)
        assert h.get("/version").json()["v"] == old


def test_every_page_has_version_marks_and_updater(server):  # noqa: F811
    base = f"http://127.0.0.1:{server}"
    urls = ["/", "/unit?appt=%d&role=doctor" % APPT, "/unit?appt=%d&role=hygienist" % APPT, "/reception", "/app",
            "/recordings", "/sent", "/today", "/mock/doctor"]
    with httpx.Client(base_url=base) as h:
        ver = h.get("/version").json()["v"]
        for u in urls:
            r = h.get(u)
            assert r.status_code == 200, u
            for tag in re.findall(r"(?:src|href)=['\"](/static/[^'\"]+\.(?:js|css)[^'\"]*)['\"]", r.text):
                assert tag.endswith(f"?v={ver}"), (u, tag)
            assert "/static/js/updater.js" in r.text and f"CV_VERSION='{ver}'" in r.text, u


def test_button_appears_only_for_new_version_and_reload_is_manual(server, browser):  # noqa: F811
    base = f"http://127.0.0.1:{server}"
    pg = page(browser, f"{base}/unit?appt={APPT}&role=doctor")
    pg.wait_for_selector('[data-part="intraoral-photos"]')
    pg.evaluate("window.__mark = 1")
    time.sleep(1.2)
    assert pg.locator("#cv-update:visible").count() == 0  # 同じ版では出ない
    with new_version():
        pg.wait_for_selector("#cv-update", state="visible", timeout=8000)
        b = pg.locator("#cv-update")
        assert b.inner_text() == "新しい版があります。更新するにはここをクリック"
        box = b.bounding_box()  # 下いっぱいの帯。高さは最低限、字は本文より大きい
        assert box["x"] <= 1 and box["width"] >= 1900 and box["y"] + box["height"] >= 1029 and box["height"] <= 60
        assert float(b.evaluate("e => parseFloat(getComputedStyle(e).fontSize)")) > float(
            pg.evaluate("parseFloat(getComputedStyle(document.body).fontSize)"))
        pg.evaluate("""() => { const q = document.createElement('div'); q.id = 'num-questions';
          q.style.cssText = 'position:fixed;left:0;right:0;bottom:36px;height:60px'; q.innerHTML = '<span>前回は何をした？</span>';
          document.body.appendChild(q); }""")
        time.sleep(0.8)  # 質問のボタンと重なるときは帯が上に出る
        assert pg.locator("#cv-update").bounding_box()["y"] + pg.locator("#cv-update").bounding_box()["height"] <=             pg.locator("#num-questions").bounding_box()["y"] + 1
        pg.evaluate("document.getElementById('num-questions').remove()")
        time.sleep(1.5)
        assert pg.evaluate("window.__mark") == 1  # 勝手には読み直さない
        b.click()
        pg.wait_for_function("window.__mark === undefined", timeout=8000)
        pg.wait_for_selector("#cv-updated")
        assert re.fullmatch(r"更新しました \d\d:\d\d", pg.inner_text("#cv-updated"))
    pg.wait_for_function("!document.querySelector('#cv-updated')", timeout=6000)  # 3秒で消える
    pg.context.close()


def test_press_in_one_tab_reloads_all_tabs_and_keeps_inner_screen(server, browser):  # noqa: F811
    base = f"http://127.0.0.1:{server}"
    ctx = browser.new_context(viewport={"width": 1920, "height": 1030})
    a = page(browser, f"{base}/unit?appt={APPT}&role=hygienist", ctx)
    b = page(browser, f"{base}/app?go=" + f"/unit%3Fappt%3D{APPT}%26role%3Ddoctor", ctx)
    c = page(browser, f"{base}/sent", ctx)
    for p in (a, b, c):
        p.wait_for_load_state("load")
        p.evaluate("window.__mark = 1")
    b.wait_for_function("document.getElementById('inner').contentWindow.document.querySelector('[data-part=\"intraoral-photos\"]')")
    with new_version():
        c.wait_for_selector("#cv-update", state="visible", timeout=8000)
        b.wait_for_selector("#cv-update", state="attached", timeout=8000)  # 帯の出る早さは画面ごとに少しずれる
        assert b.locator("#cv-update").count() == 1  # 親の画面に1つだけ（中の画面には出ない）
        assert b.frame_locator("#inner").locator("#cv-update").count() == 0
        c.click("#cv-update")  # どこで押しても全部が新しくなる
        for p in (a, b, c):
            p.wait_for_function("window.__mark === undefined", timeout=10000)
        b.wait_for_function("document.getElementById('inner').contentWindow.location.pathname === '/unit'")
        assert f"appt={APPT}" in b.evaluate("document.getElementById('inner').contentWindow.location.search")
        assert "doctor" in b.evaluate("document.getElementById('inner').contentWindow.location.search")
    ctx.close()


def test_waits_while_recording_or_editing(server, browser):  # noqa: F811
    base = f"http://127.0.0.1:{server}"
    pg = page(browser, f"{base}/app?go=" + f"/unit%3Fappt%3D{APPT}%26role%3Ddoctor")
    pg.wait_for_function("window.CVRec && document.getElementById('inner').contentWindow.document.querySelector('[data-part=\"intraoral-photos\"]')")
    pg.evaluate("window.__mark = 1; window.__realMode = CVRec.mode; CVRec.mode = () => 'recording'")
    with new_version():
        pg.wait_for_selector("#cv-update", state="visible", timeout=8000)
        pg.click("#cv-update")
        time.sleep(3)
        assert pg.evaluate("window.__mark") == 1  # 録音中は読み直さない（録音が消えない）
        pg.evaluate("CVRec.mode = window.__realMode")  # 終わったら読み直す
        pg.wait_for_function("window.__mark === undefined", timeout=10000)
    # 歯周検査を入力している途中も待つ
    pg2 = page(browser, f"{base}/unit?appt={APPT}&role=hygienist")
    pg2.wait_for_selector('[data-part="perio-exam"]')
    pg2.evaluate("window.__mark = 1; document.body.classList.add('perio-editing')")
    with new_version():
        pg2.wait_for_selector("#cv-update", state="visible", timeout=8000)
        pg2.click("#cv-update")
        time.sleep(2.5)
        assert pg2.evaluate("window.__mark") == 1
        pg2.evaluate("document.body.classList.remove('perio-editing')")
        pg2.wait_for_function("window.__mark === undefined", timeout=10000)
    pg.context.close()
    pg2.context.close()


def test_mobile_page_shows_update_button(server, browser, mobile):  # noqa: F811
    base = f"http://127.0.0.1:{mobile}"
    assert re.fullmatch(r"\d+", httpx.get(base + "/m/version").json()["v"])
    pg = page(browser, f"{base}/m/{link()}")
    pg.wait_for_load_state("load")
    pg.evaluate("window.__mark = 1")
    assert pg.locator("#cv-update:visible").count() == 0
    with new_version():
        pg.wait_for_selector("#cv-update", state="visible", timeout=8000)
        pg.click("#cv-update")
        pg.wait_for_function("window.__mark === undefined", timeout=10000)
        assert "更新しました" in pg.inner_text("#cv-updated")
    pg.context.close()
