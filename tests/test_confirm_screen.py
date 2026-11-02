"""G19: 下書きの確定・後で直す・止める・一覧の印の画面の試験（Edge）。"""
import json
import os
import time
from pathlib import Path

import httpx
import pytest

from app.ai import memo
from app.db import connect, update
from app.views import data as D
from tests.screen_helper import browser, open_page, server  # noqa: F401

FAKE = Path(os.environ["CHAIRSIDE_AI_FAKE_FILE"])
TALK = "今日は右下6番の根管充填をしました。今後の治療計画は、右下6番は被せ物を入れます。"
GOOD = json.dumps({**{k: [] for k in memo.KEYS},
                   "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"}],
                   "future_plan": [{"text": "右下6番は被せ物を入れる", "quote": "右下6番は被せ物を入れます"}]}, ensure_ascii=False)


def set_fake(reply=GOOD, transcript=TALK):
    FAKE.write_text(json.dumps({"reply": reply, "transcript": transcript}), encoding="utf-8")


@pytest.fixture(autouse=True)
def clean():
    update.update()
    c = connect()
    max_note = c.execute("SELECT COALESCE(MAX(id), 0) FROM clinical_notes").fetchone()[0]
    max_plan = c.execute("SELECT COALESCE(MAX(id), 0) FROM treatment_plans").fetchone()[0]
    c.close()

    def restore():
        c = connect()
        c.execute("DELETE FROM drafts WHERE recording_id IS NOT NULL")
        c.execute("DELETE FROM recordings")
        c.execute("DELETE FROM clinical_notes WHERE id > ?", (max_note,))
        c.execute("DELETE FROM treatment_plans WHERE id > ?", (max_plan,))
        c.execute("UPDATE treatment_plans SET superseded_on = NULL")
        c.commit()
        c.close()

    restore()
    set_fake()
    yield
    restore()
    FAKE.write_text(json.dumps({"reply": '{"result":"unclear"}', "delay_ms": 0}), encoding="utf-8")


def appt_of(chart, role=None):
    with D.con() as c:
        sql = ("SELECT a.id, a.role FROM appointments a JOIN patients p ON p.id = a.patient_id WHERE p.chart_no = ? "
               "AND a.appt_date = '2026-11-06' AND a.status = 'booked' ORDER BY a.start_time")
        rows = c.execute(sql, (chart,)).fetchall()
    return next(r[0] for r in rows if role is None or r[1] == role)


def make_rec(server, chart="0123", with_audio=True):  # noqa: F811
    base = f"http://127.0.0.1:{server}"
    with httpx.Client(base_url=base, timeout=20) as h:
        r = h.post("/rec/start", json={"appt": appt_of(chart, "doctor")}).json()
        h.post(f"/rec/{r['id']}/audio?dur=12", content=b"fake-webm-bytes")
        h.post(f"/rec/{r['id']}/transfer", json={})
        for _ in range(100):
            s = h.get(f"/api/recordings/{r['id']}").json()
            if s["state"] in ("下書き", "失敗"):
                return s
            time.sleep(0.1)
    raise AssertionError("下書きにならない")


def db_one(sql, *a):
    c = connect()
    r = c.execute(sql, a).fetchone()
    c.close()
    return r


def open_draft(browser, server, draft_id, fix=False):  # noqa: F811
    return open_page(browser, server, f"/drafts/{draft_id}" + ("?fix=1" if fix else "")), None


def ready(pg):
    pg.wait_for_function("document.body.dataset.ready === '1'")


def test_edit_items_and_plans_then_confirm(server, browser):  # noqa: F811
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"])
    ready(pg)
    assert "下書き まだ記録に入っていません" in pg.inner_text("[data-part=draft-mark]")
    notes_before = db_one("SELECT COUNT(*) FROM clinical_notes")[0]
    # キーボードで直す: 書き換え、行を足し、行を消す
    first = pg.locator("[data-section=done] .tx").first
    first.click()
    pg.keyboard.press("Control+A")
    pg.keyboard.type("右下6番の根管充填（直した）")
    pg.click("[data-section=explained] .add")
    pg.keyboard.type("違和感が出るかもしれない")
    pg.click("[data-section=done] .add")
    pg.keyboard.type("消す行")
    pg.locator("[data-section=done] li.row").last.locator(".del").click()
    # 治療計画: 今の計画と新しい計画を並べる。話に出ていない歯はそのまま残る
    rows = pg.locator("#plan-rows tr")
    texts = rows.all_inner_texts()
    assert any("右下6番" in t and "被せ物" in t for t in texts)
    left7 = next(t for t in texts if "左下7番" in t)
    assert "そのまま残ります" in left7
    r6 = pg.locator("#plan-rows tr", has_text="被せ物").first
    r6.locator("input[data-key^=c]").check()
    assert db_one("SELECT COUNT(*) FROM clinical_notes")[0] == notes_before  # 確定前は入らない
    pg.click("#btn-confirm")
    pg.wait_for_function("document.body.dataset.status === 'confirmed'")
    assert "確定済み" in pg.inner_text("[data-part=draft-mark]")
    note = db_one("SELECT * FROM clinical_notes ORDER BY id DESC LIMIT 1")
    assert db_one("SELECT COUNT(*) FROM clinical_notes")[0] == notes_before + 1
    assert "直した" in note["body"] and "違和感" in note["body"] and "消す行" not in note["body"]
    active = [r[0] for r in connect().execute("SELECT body FROM treatment_plans WHERE kind='plan' AND superseded_on IS NULL "
                                              "AND patient_id = 1")]
    assert any("左下7番" in b for b in active) and "右下6番は被せ物を入れる" in active
    assert db_one("SELECT COUNT(*) FROM treatment_plans WHERE superseded_on = '2026-11-06' AND patient_id = 1")[0] == 1
    pg.close()


def test_later_then_today_mark_then_fix_and_confirm(server, browser):  # noqa: F811
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"])
    ready(pg)
    pg.click("#btn-later")
    pg.wait_for_function("document.body.dataset.recState === '後で直す'")
    assert db_one("SELECT state FROM recordings WHERE id = ?", s["id"])[0] == "後で直す"
    assert (Path(os.environ.get("CV_DATA_DIR", Path(__file__).resolve().parents[1] / "data" / "runtime")) / "audio" /
            f"rec_{s['id']}.webm").exists()  # 音声を残す

    t = open_page(browser, server, "/today")
    t.wait_for_selector(".addendum")
    assert "大川内先生 追記必要" in t.inner_text(".addendum")
    assert t.evaluate("getComputedStyle(document.querySelector('.addendum')).animationName") == "recblink"  # 点滅
    assert t.evaluate("getComputedStyle(document.querySelector('.addendum')).color") == "rgb(198, 40, 40)"  # 赤
    assert [x.strip() for x in t.locator("thead th").all_inner_texts()] == ["時間", "カルテ番号", "氏名", "処置", "状態"]
    assert "●●" in t.inner_text("#today-rows tr")  # 氏名は伏せ字
    assert t.locator(".addendum").count() == 1  # 後で直す人だけ

    f = open_page(browser, server, f"/fix/{s['id']}")
    f.wait_for_selector("[data-part=fix-audio]")  # 音声を聞きながら
    assert f.locator("#fix-text").is_visible()
    f.wait_for_selector("[data-section=done] .tx")
    ready(f)
    f.click("#btn-confirm")
    f.wait_for_function("document.body.dataset.status === 'confirmed'")
    t.wait_for_selector(".addendum", state="detached", timeout=8000)  # 確定すると消える
    assert db_one("SELECT audio_file FROM recordings WHERE id = ?", s["id"])[0] == ""  # 確定したら音声を消す
    for p in (pg, t, f):
        p.close()


def test_leaving_patient_with_draft_is_stopped(server, browser):  # noqa: F811
    s = make_rec(server)
    appt = appt_of("0123", "doctor")
    pg = open_page(browser, server, f"/unit?appt={appt}&role=doctor")
    pg.wait_for_selector("[data-part=important]")
    pg.click("[data-action=change-patient]")
    pg.wait_for_selector("#memo-block")
    assert "確定していない診療メモがあります" in pg.inner_text("#memo-block")
    assert [b.strip() for b in pg.locator("#memo-block button").all_inner_texts()] == ["メモを開く", "後で直す"]
    assert "/unit" in pg.url  # 止まっている
    pg.click("#memo-block [data-action=memo-open]")
    pg.wait_for_url(f"**/drafts/{s['draft_id']}")
    pg.goto(f"http://127.0.0.1:{server}/unit?appt={appt}&role=doctor")
    pg.wait_for_selector("[data-part=important]")
    pg.click("[data-action=change-patient]")
    pg.wait_for_selector("#memo-block")
    pg.click("#memo-block [data-action=memo-later]")
    pg.wait_for_url(f"http://127.0.0.1:{server}/")
    assert db_one("SELECT state FROM recordings WHERE id = ?", s["id"])[0] == "後で直す"
    # 確定した人には止めない
    pg.close()


def test_failed_goes_later_then_fix_by_fixing_transcript(server, browser):  # noqa: F811
    set_fake(reply="JSONではない", transcript=TALK)
    s = make_rec(server)
    assert s["state"] == "失敗"
    appt = appt_of("0123", "doctor")
    pg = open_page(browser, server, f"/unit?appt={appt}&role=doctor")
    pg.wait_for_selector("[data-part=important]")
    pg.click("[data-action=change-patient]")
    pg.wait_for_selector("#memo-block")  # 失敗でも、音声と診療回を残して進める
    pg.click("#memo-block [data-action=memo-later]")
    pg.wait_for_url(f"http://127.0.0.1:{server}/")
    row = db_one("SELECT * FROM recordings WHERE id = ?", s["id"])
    assert row["state"] == "後で直す" and row["audio_file"] and row["visit_id"] and row["patient_id"]
    set_fake(reply=GOOD, transcript=TALK)  # あとで直す。その場では話し直さない
    f = open_page(browser, server, f"/fix/{s['id']}")
    f.wait_for_selector("#fix-text")
    f.fill("#fix-text", TALK + "（直した文字）")
    f.click("#fix-reorg")
    f.wait_for_function("location.pathname.startsWith('/drafts/')", timeout=15000)  # 新しい下書きの画面へ
    ready(f)
    assert "下書き まだ記録に入っていません" in f.inner_text("[data-part=draft-mark]")  # 人が見てから確定
    assert db_one("SELECT COUNT(*) FROM clinical_notes WHERE body LIKE '%被せ物%'")[0] == 0
    assert "直した文字" in f.inner_text("[data-part=draft-transcript]") or "直した文字" in f.locator("[data-part=draft-transcript]").inner_html()
    f.click("#btn-confirm")
    f.wait_for_function("document.body.dataset.status === 'confirmed'")
    assert db_one("SELECT state FROM recordings WHERE id = ?", s["id"])[0] == "確定"
    pg.close()
    f.close()


def test_voice_confirm_needs_second_word(server, browser):  # noqa: F811
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"])
    ready(pg)
    pg.evaluate("window.cvTyped('確定')")  # いきなり「確定」では確定しない
    assert pg.evaluate("document.body.dataset.status") == "draft"
    pg.evaluate("window.cvTyped('確定する')")
    assert "もう一度「確定」" in pg.inner_text("#msg")
    assert pg.evaluate("document.body.dataset.status") == "draft"  # まだ入らない
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "draft"
    pg.evaluate("window.cvTyped('確定')")
    pg.wait_for_function("document.body.dataset.status === 'confirmed'")
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "confirmed"
    pg.close()
