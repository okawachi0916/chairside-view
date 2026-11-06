"""G20: 最小版の通しの試験。院長が声で通す流れを、文字の口 (cvTyped) と偽物の Claude で通す。
  seed → 予約一覧で 0123 の RCT → 重要事項の全画面 → 3番の拡大と一覧 → 「前回は何をした？」 →
  録音を止めると自動で下書き→確定 → ボタン3で隠して戻す → 次の患者様 0456 の SPT (前の人が残っていない)。"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.ai import memo
from app.ai.records import build_records
from app.db import connect
from app.views import data as D
from tests.screen_helper import ROOT, open_page, server  # noqa: F401

FAKE = Path(os.environ["CHAIRSIDE_AI_FAKE_FILE"])
KEY3 = json.loads((ROOT / "config" / "keys.json").read_text(encoding="utf-8"))["button3"].replace("Ctrl", "Control")
TALK = "今日は右下6番の根管充填をしました。次回は被せ物の型を取ります。"
GOOD = json.dumps({**{k: [] for k in memo.KEYS},
                   "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"}]}, ensure_ascii=False)


def fake(reply, transcript=TALK):
    FAKE.write_text(json.dumps({"reply": reply, "transcript": transcript, "delay_ms": 0}), encoding="utf-8")


@pytest.fixture(autouse=True)
def reset_fake():
    yield
    FAKE.write_text(json.dumps({"reply": '{"result":"unclear"}', "delay_ms": 0}), encoding="utf-8")


def say(pg, word):
    pg.evaluate("w => window.cvTyped(w)", word)


def gone(pg, selector):
    pg.wait_for_function("s => document.querySelectorAll(s).length === 0", arg=selector)


def pick(pg, chart, proc):
    """予約一覧で、カルテ番号と処置が合う行を選ぶ。"""
    row = pg.locator(f'tr.row[data-proc="{proc}"]', has_text=chart)
    assert row.count() == 1
    row.click()
    pg.wait_for_url("**/unit?appt=*")
    return int(pg.url.split("appt=")[1].split("&")[0])


def with_typed(pg, appt, role):
    """文字の口を出す (声が使えないとき・試験用)。入力欄は隠す。"""
    pg.goto(pg.url.split("/unit")[0] + f"/unit?appt={appt}&role={role}&typed=1&hide=1")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("typeof window.cvTyped === 'function' && typeof window.CVAsk === 'function' "
                         "&& window.VoiceKeys && document.getElementById('band')")
    time.sleep(0.3)


def press(frame, name, times=1):
    """中の画面でボタンの鍵を押す。2回押しは0.4秒以内。"""
    for _ in range(times):
        frame.evaluate("k => window.dispatchEvent(new KeyboardEvent('keydown', {code: k, key: k, ctrlKey: true, shiftKey: true, bubbles: true}))", name)
        time.sleep(0.08)


@pytest.fixture(scope="module")
def browser():  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        yield b
        b.close()


def seed():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, r.stdout + r.stderr


def test_whole_flow(server, browser):  # noqa: F811
    # 1. 初期の状態に戻す。終わったらもう一度戻し、ほかの試験に確定した診療メモなどを残さない
    seed()
    try:
        flow(server, browser)
    finally:
        seed()


def flow(server, browser):  # noqa: F811
    base = f"http://127.0.0.1:{server}"
    with D.con() as c:
        p1 = dict(c.execute("SELECT * FROM patients WHERE chart_no = '0123'").fetchone())
        notes_before = c.execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0]
        important = [x["body"] for x in c.execute("SELECT body FROM important_notes WHERE patient_id = ?", (p1["id"],))]
        last_note = build_records(c, p1["id"])
        last_ref = next(x for x in last_note if x.ref.startswith("note:"))

    # 2. 予約一覧で 0123 の RCT の行を選ぶ
    pg = open_page(browser, server, "/clinic")
    pg.wait_for_selector("tr.row")
    appt = pick(pg, "0123", "RCT")
    assert "role=doctor" in pg.url
    with_typed(pg, appt, "doctor")
    assert "0123" in pg.inner_text(".topbar")

    # 3. 丸の番号で重要事項（1番）を開き、「戻して」で戻す
    pg.evaluate("window.cvNumbers(true)")
    assert pg.locator(".num-badge").count() == 9  # 6つの部品と「言える言葉」と「役割を変える」と「スマホ」
    say(pg, "1番")
    pg.wait_for_selector('[data-fs-panel="important"]')
    panel = pg.inner_text('[data-fs-panel="important"]')
    assert all(b in panel for b in important)
    assert pg.locator(".num-badge").count() == 0  # 全画面の中に番号は付けない
    pg.evaluate("window.cvNumbers(true)")  # 全画面の中では上の帯だけ暗くなり、例文が出る
    assert "「戻して」" in pg.inner_text("#num-band") and pg.locator("#num-dim").count() == 0
    say(pg, "もとに戻す")
    gone(pg, "[data-fs-panel]")
    assert pg.locator('[data-part="today-treatment"]').is_visible()
    say(pg, "重要事項を全画面にして")  # 言葉でも開く
    pg.wait_for_selector('[data-fs-panel="important"]')
    say(pg, "戻して")
    gone(pg, "[data-fs-panel]")

    # 4. 丸の番号で口腔内写真（6番）を開き、中では「3番を拡大して」。一覧に戻す
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "6番")
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    say(pg, "3番を拡大して")
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"] .fs-fig')
    assert pg.locator(".fs-fig").evaluate_all("els => els.map(e => Number(e.dataset.n))") == [3]
    assert pg.locator(".fs-fig img").first.evaluate("i => i.complete && i.naturalWidth > 0")
    say(pg, "一覧に戻す")
    gone(pg, "[data-fs-panel]")
    assert pg.locator('[data-part="photo-list"]').is_visible()
    say(pg, "口腔内写真の3番を拡大して")  # いつもの画面からでも開く
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"] .fs-fig')
    say(pg, "戻して")
    gone(pg, "[data-fs-panel]")

    # 5. 「前回は何をした？」と聞いて記録を見て、戻す。答えは記録そのまま
    fake(json.dumps({"result": "found", "record": last_ref.number}))
    say(pg, "前回は何をした？")
    pg.wait_for_selector('[data-fs-panel="answer"]')
    shown = pg.inner_text(".ai-frame")
    assert all(line in shown for line in last_ref.lines)
    assert "出どころ" in pg.inner_text(".ai-src")
    pg.evaluate("window.cvNumbers(true)")
    assert pg.inner_text("#num-band").strip() == "「戻して」"  # 答えの画面は「戻して」だけ
    say(pg, "戻して")
    gone(pg, '[data-fs-panel="answer"]')

    # 6. ボタン1で録音を始めて止める。何も押さなくても下書きができ、窓に出て、話した内容の欄が変わる。確定するまで診療メモには入らない
    fake(GOOD)
    with D.con() as c:
        assert c.execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0] == notes_before
    ctx = browser.new_context(viewport={"width": 1920, "height": 1030}, permissions=["microphone"])
    ap = ctx.new_page()
    ap.goto(base + "/app")
    ap.wait_for_function("document.body.dataset.rec === 'idle'")
    ap.evaluate("u => { document.getElementById('inner').src = u }", f"/unit?appt={appt}&role=doctor&typed=1&hide=1")
    ap.wait_for_function("(() => { const d = document.getElementById('inner').contentDocument; "
                         "return !!(d && d.querySelector('[data-part=spoken-summary]') && d.getElementById('band')) })()")
    time.sleep(0.5)
    inner = next(f for f in ap.frames if f != ap.main_frame)
    column = lambda: inner.locator('[data-part="spoken-summary"] li').all_inner_texts()  # noqa: E731
    assert any("側方加圧" in t for t in column())  # 録音の下書きが無いので見本の文
    press(inner, "F6", 2)
    ap.wait_for_function("document.body.dataset.rec === 'recording'")
    time.sleep(0.8)
    press(inner, "F6", 1)  # 止めるのは1回
    ap.wait_for_function("document.getElementById('rec-win').textContent.includes('下書きができました')", timeout=20000)
    assert ap.locator("#rec-win .ok").count() == 0
    # 見本の文にも「根管充填」があるので、それでは待ちにならない。新しい下書きの文が先頭に来るまで待つ（欄は窓のあとに読み直される）
    ap.wait_for_function("(() => { const li = document.getElementById('inner').contentDocument"
                         ".querySelector('[data-part=spoken-summary] li'); return !!li && li.innerText.includes('右下6番の根管充填') })()")
    now = column()
    assert "右下6番の根管充填" in now[0] and any("側方加圧" in t for t in now[1:])  # 新しい順。見本の下書きも同じ扱いで後ろ
    with D.con() as c:
        assert c.execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0] == notes_before
    ap.locator("#rec-win").click()  # 窓を押すと下書きの画面
    ap.wait_for_function("((d) => !!(d && d.body && d.body.dataset.page === 'draft'))(document.getElementById('inner').contentDocument)")
    inner = next(f for f in ap.frames if f != ap.main_frame)
    inner.wait_for_function("document.body.dataset.ready === '1'")
    assert "まだ記録に入っていません" in inner.inner_text("[data-part=draft-mark]")
    inner.evaluate("window.cvTyped('確定する')")  # G19m: 1回言えば記録する（2回目を待たない）
    # 確定すると診療の画面などへ自動で戻るので、画面ではなく記録に入ったことで確かめる
    for _ in range(100):
        with D.con() as c:
            if c.execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0] == notes_before + 1:
                break
        time.sleep(0.1)
    with D.con() as c:
        assert c.execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0] == notes_before + 1
        assert "根管充填" in c.execute("SELECT body FROM clinical_notes ORDER BY id DESC LIMIT 1").fetchone()[0]
    ctx.close()

    # 7. ボタン3で隠して戻す
    with_typed(pg, appt, "doctor")
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="hidden-screen"]')
    gone(pg, '[data-part="important"]')
    assert p1["name"] not in pg.inner_text("body") and important[0] not in pg.inner_text("body")
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="important"]')
    assert important[0] in pg.inner_text("body")

    # 8. 次の患者様 0456 の SPT の行を開く。前の人が残っていない
    pg.click("[data-action=change-patient]")
    pg.wait_for_url(base + "/clinic")  # 確定済みなので止められない
    pg.wait_for_selector("tr.row")
    appt2 = pick(pg, "0456", "SPT")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("document.body.innerText.includes('0456')")
    text = pg.inner_text("body")
    assert "0123" not in text and p1["name"] not in text
    assert all(b not in text for b in important)
    assert "根管充填をしました" not in text
    assert pg.locator("[data-fs-panel]").count() == 0 and pg.locator('[data-part="hidden-screen"]').count() == 0
    assert pg.evaluate("window.sessionStorage.length + window.localStorage.length") == 0
    assert appt2 != appt
    pg.close()
