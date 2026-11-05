"""G19・下書きの画面の簡単化: 記録する・あとで直す・戻る・止める・一覧の印の画面の試験（Edge）。"""
import json
import os
import time
from pathlib import Path

import httpx
import pytest

from app.ai import memo
from tests.polish_helper import polish_reply
from app.db import connect, update
from app.views import data as D
from tests.screen_helper import browser, open_page, server  # noqa: F401

FAKE = Path(os.environ["CHAIRSIDE_AI_FAKE_FILE"])
TALK = "今日は右下6番の根管充填をしました。今後の治療計画は、右下6番は被せ物を入れます。"
GOOD = json.dumps({**{k: [] for k in memo.KEYS},
                   "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"}],
                   "future_plan": [{"text": "右下6番は被せ物を入れる", "quote": "右下6番は被せ物を入れます"}]}, ensure_ascii=False)


def set_fake(reply=GOOD, transcript=TALK, polish_reply=None):
    cfg = {"reply": reply, "transcript": transcript}
    if polish_reply is not None:  # 無ければ、清書は聞き取りの文をそのまま返す
        cfg["polish_reply"] = polish_reply
    FAKE.write_text(json.dumps(cfg), encoding="utf-8")


@pytest.fixture(autouse=True)
def clean():
    update.update()
    c = connect()
    max_note = c.execute("SELECT COALESCE(MAX(id), 0) FROM clinical_notes").fetchone()[0]
    max_plan = c.execute("SELECT COALESCE(MAX(id), 0) FROM treatment_plans").fetchone()[0]
    appts = [tuple(r) for r in c.execute("SELECT id, status FROM appointments")]
    c.close()

    def restore():
        c = connect()
        from app.ai.journal import undo

        for (did,) in c.execute("SELECT draft_id FROM record_changes GROUP BY draft_id ORDER BY MAX(id) DESC").fetchall():
            undo(c, did)  # 試験で記録した分（歯の状態・治療歴・次回の予定・治療方針・予約の済み）を、新しい記録から順に戻す（G19m）
        c.executemany("UPDATE appointments SET status = ? WHERE id = ?", [(st, i) for i, st in appts])
        c.execute("DELETE FROM drafts WHERE recording_id IS NOT NULL")
        c.execute("DELETE FROM recordings")
        c.execute("DELETE FROM clinical_notes WHERE id > ?", (max_note,))
        c.execute("DELETE FROM treatment_plans WHERE id > ?", (max_plan,))
        c.execute("UPDATE treatment_plans SET superseded_on = NULL")  # 試験用の下書きでは、方針・次回の予定を印なしで外すので、見本の分は戻る
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
               "AND a.appt_date = '2026-11-06' AND a.status IN ('booked', 'done') ORDER BY a.start_time")
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


def open_draft(browser, server, draft_id, fix=False, back="/recordings"):  # noqa: F811
    url = f"/drafts/{draft_id}?back={back}" + ("&fix=1" if fix else "")
    return open_page(browser, server, url), None


def home(server, path="/recordings"):
    return f"http://127.0.0.1:{server}{path}"


def ready(pg):
    pg.wait_for_function("document.body.dataset.ready === '1'")


def test_edit_items_and_plans_then_record(server, browser):  # noqa: F811
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"])
    ready(pg)
    assert "下書き まだ記録に入っていません" in pg.inner_text("[data-part=draft-mark]")
    notes_before = db_one("SELECT COUNT(*) FROM clinical_notes")[0]
    # ボタンは「カルテに記録する」と「あとで直す」の2つだけ。「保存」は無い
    assert [b.strip() for b in pg.locator(".draft-actions button").all_inner_texts()] == ["カルテに記録する", "あとで直す"]
    assert pg.locator("#btn-save").count() == 0
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
    # 保存のボタンは押さない。直した所は、その場で自動で保存される
    pg.wait_for_function("document.body.dataset.autosave === 'saved'")
    saved = json.loads(db_one("SELECT items FROM drafts WHERE id = ?", s["draft_id"])[0])
    assert any("直した" in r["text"] for r in saved["done"]) and any("違和感" in r["text"] for r in saved["explained"])
    assert not any("消す行" in r["text"] for r in saved["done"])
    assert db_one("SELECT COUNT(*) FROM clinical_notes")[0] == notes_before  # 記録するまでは入らない
    # 治療計画の変更: 今の計画と新しい計画を並べる。話に出ていない歯はそのまま残る
    texts = pg.locator("#plan-rows tr").all_inner_texts()
    assert any("右下6番" in t and "被せ物" in t for t in texts)
    left7 = next(t for t in texts if "左下7番" in t)
    assert "そのまま残す" in left7
    assert pg.locator("#plan-rows tr", has_text="左下7番").locator("input[data-key^=d]").is_checked() is False  # 削除は印なし
    r6 = pg.locator("#plan-rows tr", has_text="被せ物").first
    r6.locator("input[data-key^=c]").check()
    assert db_one("SELECT COUNT(*) FROM clinical_notes")[0] == notes_before
    pg.click("#btn-confirm")
    pg.wait_for_url(home(server))  # 押したら、来た画面へ自動で戻る
    note = db_one("SELECT * FROM clinical_notes ORDER BY id DESC LIMIT 1")
    assert db_one("SELECT COUNT(*) FROM clinical_notes")[0] == notes_before + 1
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "confirmed"
    assert "直した" in note["body"] and "違和感" in note["body"] and "消す行" not in note["body"]
    active = [r[0] for r in connect().execute("SELECT body FROM treatment_plans WHERE kind='plan' AND superseded_on IS NULL "
                                              "AND patient_id = 1")]
    assert any("左下7番" in b for b in active) and "右下6番は被せ物を入れる" in active
    assert db_one("SELECT COUNT(*) FROM treatment_plans WHERE superseded_on = '2026-11-06' AND patient_id = 1")[0] == 1
    pg.close()


def test_plan_defaults_and_layout(server, browser):  # noqa: F811
    set_fake(reply=json.dumps({**{k: [] for k in memo.KEYS},
                               "future_plan": [{"text": "左上3番は経過観察をする", "quote": "右下6番は被せ物を入れます"}]},
                              ensure_ascii=False))
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"])
    ready(pg)
    assert pg.locator("#plan-compare h2").inner_text().strip() == "治療計画の変更"
    # 今の計画の行: 削除は印なし（そのまま残す）
    existing = pg.locator("#plan-rows tr:not(.add)")
    assert existing.count() >= 3
    for tr in existing.all():
        assert tr.locator("input[data-key^=d]").is_checked() is False
    # 新しく出た計画: 追加するは印あり
    add = pg.locator("#plan-rows tr.add")
    assert add.count() == 1 and add.locator("input[data-key^='a:']").is_checked() is True
    # 見出しは表の上、表は全部の幅（左に縦に寄らない）、右の項目の下を隠さない
    h2, table = pg.locator("#plan-compare h2").bounding_box(), pg.locator("#plan-compare table").bounding_box()
    right, cols = pg.locator(".draft-right").bounding_box(), pg.locator(".draft-cols").bounding_box()
    assert h2["y"] + h2["height"] <= table["y"] + 1
    assert table["width"] > 900
    assert pg.locator("#plan-compare th").first.bounding_box()["width"] > 150
    assert table["y"] >= right["y"] + right["height"] - 1 and table["y"] >= cols["y"] + cols["height"] - 1
    assert pg.locator("[data-section=future_policy]").is_visible()
    # 見た目の部品の名前（.rec は右下に固定する録音中の札）とぶつかって、表が画面に固定されないこと
    fixed = pg.evaluate("[...document.querySelectorAll('body *')].filter(e => getComputedStyle(e).position === 'fixed').length")
    assert fixed == 0
    assert pg.evaluate("getComputedStyle(document.querySelector('#plan-compare table')).display") == "table"
    pg.close()


def test_back_button_and_voice_keep_draft_and_go_back(server, browser):  # noqa: F811
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"], back="/today")
    ready(pg)
    assert pg.locator("#btn-back").inner_text().strip() == "戻る"
    box = pg.locator("#btn-back").bounding_box()
    assert box["x"] < 200 and box["y"] < 100  # 左上
    pg.locator("[data-section=done] .tx").first.click()
    pg.keyboard.press("Control+A")
    pg.keyboard.type("戻る前に直した")
    pg.click("#btn-back")  # 保存の確認は出ない。直した所は自動で保存され、下書きのまま戻る
    pg.wait_for_url(home(server, "/today"))
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "draft"
    assert "戻る前に直した" in db_one("SELECT items FROM drafts WHERE id = ?", s["draft_id"])[0]
    # 声の「戻して」も同じ動き。「使えません」は出ない
    pg, _ = open_draft(browser, server, s["draft_id"], back="/recordings")
    ready(pg)
    pg.evaluate("window.cvTyped('見せて')")
    assert "使えません" in pg.inner_text("#msg")
    assert pg.evaluate("window.cvTyped('戻して')") == "back"
    pg.wait_for_url(home(server))
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "draft"
    pg.close()


@pytest.mark.parametrize("back", ["https://example.com/", "//example.com/x", "javascript:alert(1)", "/a b", ""])
def test_back_never_leaves_the_server(server, back):  # noqa: F811
    s = make_rec(server)
    r = httpx.get(f"http://127.0.0.1:{server}/drafts/{s['draft_id']}", params={"back": back})
    assert r.status_code == 200 and "data-back='/'" in r.text and "example.com" not in r.text.split("<body")[1]


def test_polished_text_is_the_body_and_original_is_kept(server, browser):  # noqa: F811
    talk = "今日は右下6番の根幹重点をしました。仮歯はTEKを入れました。"
    set_fake(reply=json.dumps({**{k: [] for k in memo.KEYS},
                               "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"}]}, ensure_ascii=False),
             transcript=talk, polish_reply=polish_reply(talk, [("根幹重点", "根管充填")]))
    s = make_rec(server)
    r = db_one("SELECT transcript, polished, polish FROM recordings WHERE id = ?", s["id"])
    assert r["transcript"] == talk and "根管充填" in r["polished"]  # 聞き取りのままの文字は残る。清書は別に持つ
    d = db_one("SELECT transcript, fixed_transcript, fixes FROM drafts WHERE id = ?", s["draft_id"])
    assert d["transcript"] == talk and "根管充填" in d["fixed_transcript"] and "TeC" in d["fixed_transcript"]
    assert [(f["from"], f["to"]) for f in json.loads(d["fixes"])] == [("根幹重点", "根管充填"), ("TEK", "TeC")]
    pg, _ = open_draft(browser, server, s["draft_id"])
    ready(pg)
    # 画面の本文は清書。直した言葉に下線。聞き取りのままは、押すと開く
    body = pg.locator("[data-part=draft-polished]")
    assert "根管充填をしました" in body.inner_text() and "根幹重点" not in body.inner_text()
    assert body.locator("u.pf-fix").all_inner_texts() == ["根管充填", "TeC"]
    pg.screenshot(path=str(Path(__file__).resolve().parents[1] / "docs" / "画面" / "G19k_draft.png"))
    assert not pg.locator("[data-part=draft-raw] p").is_visible()
    pg.click("[data-part=draft-raw] summary")
    assert "根幹重点" in pg.inner_text("[data-part=draft-raw] p")
    fx = pg.inner_text("[data-part=draft-fixes]")
    assert "根幹重点 → 根管充填" in fx and "TEK → TeC" in fx  # 元→直し
    assert pg.locator("[data-section=done] .tx").first.input_value() == "右下6番の根管充填。"
    pg.close()


def test_later_then_today_mark_then_fix_and_record(server, browser):  # noqa: F811
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"], back="/today")
    ready(pg)
    assert pg.locator("#btn-later").inner_text().strip() == "あとで直す"
    pg.click("#btn-later")
    pg.wait_for_url(home(server, "/today"))  # 押したら、来た画面へ自動で戻る
    assert db_one("SELECT state FROM recordings WHERE id = ?", s["id"])[0] == "後で直す"
    assert (Path(os.environ.get("CV_DATA_DIR", Path(__file__).resolve().parents[1] / "data" / "runtime")) / "audio" /
            f"rec_{s['id']}.webm").exists()  # 音声を残す

    t = pg  # 戻ってきた今日の診療一覧
    t.wait_for_selector(".addendum")
    assert "大川内先生 追記必要" in t.inner_text(".addendum")
    assert t.evaluate("getComputedStyle(document.querySelector('.addendum')).animationName") == "recblink"  # 点滅
    assert t.evaluate("getComputedStyle(document.querySelector('.addendum')).color") == "rgb(198, 40, 40)"  # 赤
    assert [x.strip() for x in t.locator("thead th").all_inner_texts()] == ["時間", "カルテ番号", "氏名", "処置", "状態"]
    assert "●●" in t.inner_text("#today-rows tr")  # 氏名は伏せ字
    assert t.locator(".addendum").count() == 1  # 後で直す人だけ
    assert t.locator("a.addendum").get_attribute("href").startswith("/drafts/")  # 印から下書きを開ける
    t.click("a.addendum")
    t.wait_for_selector("[data-part=draft-mark]")
    assert "back=" in t.url and "today" in t.url
    t.close()

    f = open_page(browser, server, f"/fix/{s['id']}?back=/today")
    f.wait_for_selector("[data-part=fix-audio]")  # 音声を聞きながら
    assert f.locator("#fix-text").is_visible()
    f.wait_for_selector("[data-section=done] .tx")
    ready(f)
    f.click("#btn-confirm")
    f.wait_for_url(home(server, "/today"))
    f.wait_for_selector(".addendum", state="detached", timeout=8000)  # 記録すると消える
    assert db_one("SELECT audio_file FROM recordings WHERE id = ?", s["id"])[0] == ""  # 記録したら音声を消す
    f.close()


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
    pg.wait_for_url(lambda u: f"/drafts/{s['draft_id']}" in u and "back=" in u)  # 記録したら、この診療の画面へ戻る
    assert "unit" in pg.url
    ready(pg)
    pg.click("#btn-back")  # 来た診療の画面へ戻る
    pg.wait_for_url(lambda u: "/unit" in u)
    pg.wait_for_selector("[data-part=important]")
    pg.click("[data-action=change-patient]")
    pg.wait_for_selector("#memo-block")
    pg.click("#memo-block [data-action=memo-later]")
    pg.wait_for_url(f"http://127.0.0.1:{server}/")
    assert db_one("SELECT state FROM recordings WHERE id = ?", s["id"])[0] == "後で直す"
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
    assert "back=" in f.url
    assert "下書き まだ記録に入っていません" in f.inner_text("[data-part=draft-mark]")  # 人が見てから記録する
    assert db_one("SELECT COUNT(*) FROM clinical_notes WHERE body LIKE '%被せ物%'")[0] == 0
    assert "直した文字" in f.inner_text("[data-part=draft-transcript]") or "直した文字" in f.locator("[data-part=draft-transcript]").inner_html()
    assert db_one("SELECT fix_off FROM recordings WHERE id = ?", s["id"])[0] == 1  # 人が直した文字は、自動の直しをしない
    f.click("#btn-confirm")
    f.wait_for_url(home(server, "/"))
    assert db_one("SELECT state FROM recordings WHERE id = ?", s["id"])[0] == "確定"
    pg.close()
    f.close()


def test_voice_confirm_is_one_time(server, browser):  # noqa: F811
    """G19m: 「確定」と言うだけで記録して、来た画面へ戻る（2回目を待たない）。"""
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"])
    ready(pg)
    pg.evaluate("window.cvTyped('確定')")
    pg.wait_for_url(home(server))
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "confirmed"
    pg.close()
