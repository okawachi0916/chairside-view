"""G17: 録音の窓と親の画面 (/app) の試験（Edge。マイクは偽物の機器）。"""
import json
import os
import time
from pathlib import Path

import pytest

from app.ai import memo
from app.db import connect, update
from app.views import data as D
from tests.screen_helper import server  # noqa: F401

FAKE = Path(os.environ["CHAIRSIDE_AI_FAKE_FILE"])
TALK = "今日は右下6番の根管充填をしました。次回は二週間後に土台を立てます。"
REPLY = json.dumps({**{k: [] for k in memo.KEYS},
                    "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"}],
                    "next_plan": [{"text": "二週間後に土台", "quote": "二週間後に土台を立てます"}]}, ensure_ascii=False)
F6 = {"code": "F6", "key": "F6"}
F7 = {"code": "F7", "key": "F7"}


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        yield b
        b.close()


def _wipe():
    c = connect()
    c.execute("DELETE FROM drafts WHERE recording_id IS NOT NULL")
    c.execute("DELETE FROM recordings")
    c.commit()
    c.close()


@pytest.fixture(autouse=True)
def clean():
    update.update()
    _wipe()
    FAKE.write_text(json.dumps({"reply": REPLY, "transcript": TALK}), encoding="utf-8")
    yield
    time.sleep(0.5)  # 裏の処理が終わってから消す（他の試験の画面に下書きを残さない）
    _wipe()
    FAKE.write_text(json.dumps({"reply": '{"result":"unclear"}', "delay_ms": 0}), encoding="utf-8")


def appt_of(chart):
    with D.con() as c:
        return c.execute("SELECT a.id FROM appointments a JOIN patients p ON p.id = a.patient_id WHERE p.chart_no = ? "
                         "AND a.appt_date = '2026-11-06' AND a.status = 'booked' ORDER BY a.start_time", (chart,)).fetchone()[0]


def rec_rows():
    c = connect()
    rows = [dict(r) for r in c.execute("SELECT * FROM recordings ORDER BY id")]
    c.close()
    return rows


def wait_db(pred, sec=15):
    t0 = time.time()
    while time.time() - t0 < sec:
        rows = rec_rows()
        if pred(rows):
            return rows
        time.sleep(0.1)
    raise AssertionError(f"待っても揃わない: {[(r['state'], r['error']) for r in rec_rows()]}")


def open_app(browser, server):  # noqa: F811
    ctx = browser.new_context(viewport={"width": 1920, "height": 1030}, permissions=["microphone"])
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{server}/app?go=/clinic")
    pg.wait_for_function("document.body.dataset.rec === 'idle'")
    pg.wait_for_function("document.getElementById('inner').contentDocument.querySelector('[data-part=appointment-list]')")
    return pg


def inner(pg):
    return next(f for f in pg.frames if f != pg.main_frame)


def go(pg, url, sel):
    pg.evaluate("u => { document.getElementById('inner').src = u }", url)
    pg.wait_for_function("s => { const d = document.getElementById('inner').contentDocument; return !!(d && d.querySelector(s)) }", arg=sel)
    time.sleep(0.3)


def press(pg, key, times=1):
    """中の画面でボタンの鍵を押す。2回押しは0.4秒以内。"""
    for _ in range(times):
        inner(pg).evaluate("k => window.dispatchEvent(new KeyboardEvent('keydown', {code: k.code, key: k.key, ctrlKey: true, shiftKey: true, bubbles: true}))", key)
        time.sleep(0.08)


def start_rec(pg):
    press(pg, F6, 2)
    pg.wait_for_function("document.body.dataset.rec === 'recording'")


def stop_rec(pg):
    press(pg, F6, 1)  # 録音中は1回で止まる。止めたあとは何も押さなくてよい
    pg.wait_for_function("document.body.dataset.rec === 'idle'")


UNIT = lambda chart: f"/unit?appt={appt_of(chart)}&role=doctor&typed=1&hide=1"  # noqa: E731


def test_patientless_recording_survives_screen_changes_and_features_work(server, browser):  # noqa: F811
    pg = open_app(browser, server)
    start_rec(pg)
    assert pg.evaluate("document.body.dataset.recFixed") == "0"  # 患者様なし
    rec_id = pg.evaluate("document.body.dataset.recId")
    pg.wait_for_function("document.getElementById('rec-win').textContent.includes('録音中 00:0')")
    win = pg.locator("#rec-win")
    box = win.bounding_box()
    assert box["x"] + box["width"] > 1700 and box["y"] + box["height"] > 900 and box["width"] < 400  # 右下の小さい窓
    assert pg.evaluate("getComputedStyle(document.querySelector('#rec-win .msg')).animationName") == "recblink"  # 点滅

    # 画面が替わっても録音と窓は切れない
    go(pg, UNIT("0123"), "[data-part=important]")
    assert pg.evaluate("document.body.dataset.rec") == "recording" and pg.evaluate("document.body.dataset.recId") == rec_id
    assert win.is_visible()
    f = inner(pg)
    # 録音中も全画面、写真の拡大、声の指示が動く
    f.evaluate("window.cvTyped('重要事項を全画面にして')")
    f.wait_for_selector('[data-fs-panel="important"]')
    f.evaluate("window.cvTyped('戻して')")
    f.wait_for_selector("[data-fs-panel]", state="detached")
    f.evaluate("window.cvTyped('口腔内写真を全画面にして')")
    f.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    f.evaluate("window.cvTyped('3番を拡大して')")
    f.wait_for_selector(".fs-item.sel")
    f.evaluate("window.cvTyped('戻して')")
    assert pg.evaluate("document.body.dataset.rec") == "recording"

    # ボタン2: 声の指示を聞く間だけ録音を止める。指示の言葉は録音に入れない
    pg.route("**/voice/transcribe", lambda r: r.fulfill(json={"text": "重要事項を全画面にして"}))
    modes = []
    pg.evaluate("""() => { window.__modes = []; setInterval(() => window.__modes.push(window.CVRec.mode()), 50); }""")
    press(pg, F7, 2)  # 声の指示を始める
    pg.wait_for_function("document.body.dataset.rec === 'paused'")
    assert "一時停止中" in pg.inner_text("#rec-win")
    time.sleep(0.6)
    press(pg, F7, 1)  # 指示を止める → 文字起こし → 操作 → 録音を続ける
    pg.wait_for_function("document.body.dataset.rec === 'recording'")
    f.wait_for_selector('[data-fs-panel="important"]')  # 指示は動いた
    time.sleep(0.3)
    modes = pg.evaluate("window.__modes")
    assert "paused" in modes and modes[-1] == "recording"
    f.evaluate("window.cvTyped('戻して')")

    time.sleep(0.8)
    stop_rec(pg)
    assert pg.locator("#rec-win .ok").count() == 0 and "録音が終わりました" not in pg.inner_text("body")  # OK の段は無い
    pg.wait_for_function("document.getElementById('rec-win').textContent.includes('転送待ちにしました')")  # 患者様なしは転送待ち
    rows = wait_db(lambda r: r and r[0]["state"] == "転送待ち" and r[0]["transcript"])
    assert rows[0]["patient_id"] is None and rows[0]["duration_sec"] > 0.5  # 声の指示の間は長さに入らない
    assert rows[0]["audio_file"]
    pg.wait_for_function("document.getElementById('rec-win').textContent.includes('転送待ち 1件')", timeout=9000)

    # 窓を押すと一覧が開き、患者様と診療回を選ぶと、その診療回の下書きになる
    win.click()
    pg.wait_for_function("((d) => !!(d && d.body && d.body.dataset.page === 'recordings'))(document.getElementById('inner').contentDocument)")
    f = inner(pg)
    f.wait_for_selector("tr[data-state='転送待ち']")
    assert [t.strip() for t in f.locator("thead th").all_inner_texts()][:4] == ["時間", "長さ", "カルテ番号", "状態"]
    assert "患者様なし" in f.inner_text("tr[data-state='転送待ち']")
    b = appt_of("0456")
    f.select_option("tr[data-state='転送待ち'] select[data-role=target]", str(b))
    f.click("tr[data-state='転送待ち'] button")
    f.wait_for_selector("tr[data-state='下書き']", timeout=15000)
    c = connect()
    d = c.execute("SELECT d.*, p.chart_no, v.appointment_id FROM drafts d JOIN patients p ON p.id = d.patient_id "
                  "JOIN visits v ON v.id = d.visit_id WHERE d.recording_id = ?", (int(rec_id),)).fetchone()
    assert d["chart_no"] == "0456" and d["appointment_id"] == b and d["status"] == "draft"
    f.click("tr[data-state='下書き'] a")
    pg.wait_for_function("((d) => !!(d && d.body && d.body.dataset.page === 'draft'))(document.getElementById('inner').contentDocument)")
    f = inner(pg)
    assert "下書き まだ記録に入っていません" in f.inner_text("[data-part=draft-mark]")
    assert "根管充填" in f.inner_text("[data-part=draft-transcript]")
    assert "二週間後に土台。" in [i.input_value() for i in f.locator("[data-part=draft-items] .tx").all()]
    pg.context.close()


def test_fixed_recording_blocks_next_patient_until_stopped(server, browser):  # noqa: F811
    pg = open_app(browser, server)
    go(pg, UNIT("0123"), "[data-part=important]")
    start_rec(pg)
    assert pg.evaluate("document.body.dataset.recFixed") == "1"
    f = inner(pg)
    f.click("[data-action=change-patient]")  # 次の患者様へ進もうとする
    pg.wait_for_function("document.getElementById('rec-win').textContent.includes('次の患者様へ進めません')")
    assert "/unit" in pg.evaluate("document.getElementById('inner').contentWindow.location.pathname")
    time.sleep(0.8)
    stop_rec(pg)
    pg.wait_for_function("document.getElementById('rec-win').textContent.match(/下書きにしています|下書きができました/)")
    # 文字起こしと整理は裏で進む。止めずに次の患者様へ進める
    f = inner(pg)
    f.click("[data-action=change-patient]")
    # 整理が先に終わっていれば「確定していない診療メモがあります」で止まる（G19）。後で直すに置いて進む
    pg.wait_for_function("document.getElementById('inner').contentWindow.location.pathname === '/' || "
                         "!!document.getElementById('inner').contentDocument.getElementById('memo-block')")
    if inner(pg).locator("#memo-block").count():
        inner(pg).click("#memo-block [data-action=memo-later]")
        pg.wait_for_function("document.getElementById('inner').contentWindow.location.pathname === '/clinic'")
    rows = wait_db(lambda r: r and r[0]["state"] in ("下書き", "後で直す"))
    c = connect()
    assert c.execute("SELECT chart_no FROM patients WHERE id = ?", (rows[0]["patient_id"],)).fetchone()[0] == "0123"
    pg.context.close()


def summary_items(pg):
    return inner(pg).locator('[data-part="spoken-summary"] li').all_inner_texts()


def test_stop_makes_draft_by_itself_and_column_changes(server, browser):  # noqa: F811
    pg = open_app(browser, server)
    go(pg, UNIT("0123"), "[data-part=important]")
    before = summary_items(pg)
    assert any("側方加圧" in t for t in before)  # 録音の下書きが無いときは見本の文
    start_rec(pg)
    time.sleep(0.8)
    stop_rec(pg)
    # 何も押さずに、転送 → 文字起こし → 整理 → 下書き。窓に出て、欄が読み直し無しで変わる
    pg.wait_for_function("document.getElementById('rec-win').textContent.includes('下書きができました')", timeout=15000)
    assert pg.locator("#rec-win .ok").count() == 0
    pg.wait_for_function("document.querySelector('#inner').contentDocument.querySelector('[data-part=spoken-summary]').innerText.includes('根管充填')")
    now = summary_items(pg)
    assert "右下6番の根管充填" in now[0] and any("側方加圧" in t for t in now[1:])  # 一番新しい下書きが先頭。見本の下書きも同じ扱いで、古いので後ろに並ぶ
    assert "根管充填をしました" in inner(pg).evaluate("document.querySelector('template[data-fs=spoken-summary]').innerHTML")
    # 窓を押すと下書きの画面が開く
    pg.locator("#rec-win").click()
    pg.wait_for_function("((d) => !!(d && d.body && d.body.dataset.page === 'draft'))(document.getElementById('inner').contentDocument)")
    pg.context.close()


def test_voice_opens_the_draft(server, browser):  # noqa: F811
    pg = open_app(browser, server)
    go(pg, UNIT("0123"), "[data-part=important]")
    f = inner(pg)
    f.evaluate("window.cvTyped('下書きを開いて')")
    pg.wait_for_function("document.getElementById('inner').contentDocument.getElementById('heard').textContent.includes('開ける下書きはありません')")
    start_rec(pg)
    time.sleep(0.8)
    stop_rec(pg)
    pg.wait_for_function("document.getElementById('rec-win').textContent.includes('下書きができました')", timeout=15000)
    inner(pg).evaluate("window.cvTyped('下書きを開いて')")
    pg.wait_for_function("((d) => !!(d && d.body && d.body.dataset.page === 'draft'))(document.getElementById('inner').contentDocument)")
    assert pg.evaluate("document.body.dataset.draftReady") == ""
    pg.context.close()


def test_new_draft_while_hidden_shows_after_restore(server, browser):  # noqa: F811
    pg = open_app(browser, server)
    go(pg, UNIT("0123"), "[data-part=important]")
    start_rec(pg)
    time.sleep(0.8)
    stop_rec(pg)
    f = inner(pg)  # 隠したままでも、下書きの内容は隠した画面に出ない
    f.evaluate("CVActions.run('hide-toggle')")
    pg.wait_for_function("document.getElementById('rec-win').textContent.includes('下書きができました')", timeout=15000)
    time.sleep(0.5)
    assert "根管充填" not in inner(pg).inner_text("body")
    f.evaluate("CVActions.run('hide-toggle')")
    pg.wait_for_function("document.querySelector('#inner').contentDocument.querySelector('[data-part=spoken-summary]').innerText.includes('右下6番の根管充填')")
    pg.context.close()


def test_patientless_recording_stays_waiting_without_ok(server, browser):  # noqa: F811
    pg = open_app(browser, server)
    start_rec(pg)
    time.sleep(0.8)
    stop_rec(pg)
    pg.wait_for_function("document.getElementById('rec-win').textContent.includes('転送待ち 1件')", timeout=9000)
    time.sleep(1.0)
    assert rec_rows()[0]["state"] == "転送待ち"
    assert connect().execute("SELECT COUNT(*) FROM drafts WHERE recording_id IS NOT NULL").fetchone()[0] == 0
    pg.context.close()


def test_failure_screen_and_retry(server, browser):  # noqa: F811
    FAKE.write_text(json.dumps({"reply": "JSONではない", "transcript": TALK}), encoding="utf-8")
    pg = open_app(browser, server)
    go(pg, UNIT("0123"), "[data-part=important]")
    start_rec(pg)
    time.sleep(0.8)
    stop_rec(pg)
    wait_db(lambda r: r and r[0]["state"] == "失敗")
    pg.evaluate("document.getElementById('inner').src = '/recordings'")
    pg.wait_for_function("((d) => !!(d && d.querySelector(\"tr[data-state='失敗']\")))(document.getElementById('inner').contentDocument)")
    f = inner(pg)
    row = f.locator("tr[data-state='失敗']")
    assert row.locator(".err").inner_text().strip() != ""  # 理由
    assert row.locator("button", has_text="再試行").count() == 1 and row.locator("button", has_text="後で直す").count() == 1
    FAKE.write_text(json.dumps({"reply": REPLY, "transcript": TALK}), encoding="utf-8")
    row.locator("button", has_text="再試行").click()
    f.wait_for_selector("tr[data-state='下書き']", timeout=15000)
    c = connect()
    assert c.execute("SELECT COUNT(*) FROM drafts WHERE recording_id IS NOT NULL").fetchone()[0] == 1
    pg.context.close()
