"""G20: 最小版の通しの試験。院長が声で通す流れを、文字の口 (cvTyped) と偽物の Claude で通す。
  seed → 予約一覧で 0123 の RCT → 重要事項の全画面 → 3番の拡大と一覧 → 「前回は何をした？」 →
  下書きを作って確定 → ボタン3で隠して戻す → 次の患者様 0456 の SPT (前の人が残っていない)。"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.ai import memo
from app.ai.records import build_records
from app.db import connect
from app.views import data as D
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401

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


def make_draft(base, appt):
    with httpx.Client(base_url=base, timeout=20) as h:
        r = h.post("/rec/start", json={"appt": appt}).json()
        h.post(f"/rec/{r['id']}/audio?dur=12", content=b"fake-webm-bytes")
        h.post(f"/rec/{r['id']}/transfer", json={})
        for _ in range(100):
            s = h.get(f"/api/recordings/{r['id']}").json()
            if s["state"] in ("下書き", "失敗"):
                return s
            time.sleep(0.1)
    raise AssertionError("下書きにならない")


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
    pg = open_page(browser, server, "/")
    pg.wait_for_selector("tr.row")
    appt = pick(pg, "0123", "RCT")
    assert "role=doctor" in pg.url
    with_typed(pg, appt, "doctor")
    assert "0123" in pg.inner_text(".topbar")

    # 3. 丸の番号で重要事項（1番）を開き、「戻して」で戻す
    pg.evaluate("window.cvNumbers(true)")
    assert pg.locator(".num-badge").count() == 6
    say(pg, "1番")
    pg.wait_for_selector('[data-fs-panel="important"]')
    panel = pg.inner_text('[data-fs-panel="important"]')
    assert all(b in panel for b in important)
    assert pg.locator(".num-badge").count() == 0  # 全画面の中に番号は付けない
    say(pg, "もとに戻す")
    gone(pg, "[data-fs-panel]")
    assert pg.locator('[data-part="today-treatment"]').is_visible()
    say(pg, "重要事項を全画面にして")  # 言葉でも開く
    pg.wait_for_selector('[data-fs-panel="important"]')
    say(pg, "戻して")
    gone(pg, "[data-fs-panel]")

    # 4. 丸の番号で口腔内写真（5番）を開き、中では「3番を拡大して」。一覧に戻す
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "5番")
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
    say(pg, "戻して")
    gone(pg, '[data-fs-panel="answer"]')

    # 6. 架空の話で下書きを作り、確定する (確定するまで診療メモには入らない)
    fake(GOOD)
    s = make_draft(base, appt)
    assert s["state"] == "下書き", s
    d = open_page(browser, server, f"/drafts/{s['draft_id']}")
    d.wait_for_function("document.body.dataset.ready === '1'")
    assert "まだ記録に入っていません" in d.inner_text("[data-part=draft-mark]")
    with D.con() as c:
        assert c.execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0] == notes_before
    d.evaluate("window.cvTyped('確定')")
    assert "先に" in d.inner_text("#msg")  # 「確定する」の前に「確定」だけでは入らない
    d.evaluate("window.cvTyped('確定する')")
    d.evaluate("window.cvTyped('確定')")
    d.wait_for_function("document.body.dataset.status === 'confirmed'")
    with D.con() as c:
        assert c.execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0] == notes_before + 1
        assert "根管充填" in c.execute("SELECT body FROM clinical_notes ORDER BY id DESC LIMIT 1").fetchone()[0]
    d.close()

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
    pg.wait_for_url(base + "/")  # 確定済みなので止められない
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
