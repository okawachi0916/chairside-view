"""G19f: 画面の日付は診療回の日付にそろえる。まとめて要約に前の診療回の分が入らない。「前回」は診療日の順。"""
import re

from app.ai import ask as ask_mod
from app.ai import recpipe, segview
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from tests.test_g19b import manual, reply_for  # noqa: F401
from tests.test_g19c import HYG_TEXT, OLD_TEXT, TODAY_TEXT, add_segment, record_as  # noqa: F401
from tests.test_rec_pipeline import EMPTY, api, appt_of, con_of, env, use, wait_state  # noqa: F401


def heads(env, appt, role="doctor"):
    html = env["client"].get(f"/api/view/unit?appt={appt}&role={role}").json()["html"]
    return re.findall(r'<h4 class="seg-day">([^<]*)</h4>', html)


def test_headings_use_the_visit_date_not_the_pc_date(manual):
    use(manual, ScriptedMouth(EMPTY), TODAY_TEXT)
    a = appt_of(manual, "0123")
    c = con_of(manual)
    day = c.execute("SELECT visit_date FROM visits v JOIN appointments p ON p.id = v.appointment_id WHERE p.id = ?", (a,)).fetchone()
    day = day[0] if day else c.execute("SELECT appt_date FROM appointments WHERE id = ?", (a,)).fetchone()[0]
    record_as(manual, a, "doctor", TODAY_TEXT)
    first = heads(manual, a)[0]
    assert first == f"{segview.date_label(day, day)} 歯科医師" and "（今日）" in first
    m, d = int(day[5:7]), int(day[8:10])
    assert first.startswith(f"{m}月{d}日")


def test_sample_earlier_segments_belong_to_earlier_visits():
    from app.db import initial
    from app.today import BASE  # 見本は BASE を「今日」として書いてある（今日へずらすのは dates.py）

    built = initial.build()
    visits = {v["id"]: v for v in built["visits"]}
    assert built["recordings"]
    for r in built["recordings"]:
        v = visits[r["visit_id"]]
        assert v["visit_date"] < BASE and r["started_at"][:10] == v["visit_date"]  # 前の診療回の日付


def test_sample_screen_shows_earlier_visit_dates(manual):
    use(manual, ScriptedMouth(EMPTY), TODAY_TEXT)
    a = appt_of(manual, "0123")
    got = heads(manual, a)
    assert any(h.startswith("10月23日") for h in got) and any(h.startswith("10月9日") for h in got)
    assert not any("（今日）" in h for h in got)  # 今日の区切りが無いので、今日の見出しは出ない


def test_combine_replaces_an_old_summary_that_included_earlier_days(manual):
    """前の版が前の診療回の分まで1つにまとめていたとき、押し直すと今日の分だけの要約に入れ替わる。"""
    mouth = use(manual, ScriptedMouth(reply_for(("右下6番の根管充填。", "根管充填をしました"))), TODAY_TEXT)
    a = appt_of(manual, "0123")
    old = add_segment(manual, a, OLD_TEXT, days=1, role="doctor")
    doc = record_as(manual, a, "doctor", TODAY_TEXT)
    c = con_of(manual)
    pid, vid = c.execute("SELECT patient_id, visit_id FROM recordings WHERE id = ?", (doc,)).fetchone()
    stale = c.execute("INSERT INTO drafts (patient_id, visit_id, kind, body, transcript, status, created_at, combined) "
                      "VALUES (?, ?, 'spoken_summary', '昔の要約', ?, 'draft', '2026-11-03 10:00', 1)",
                      (pid, vid, OLD_TEXT + TODAY_TEXT)).lastrowid
    c.execute("UPDATE recordings SET state = '下書き', draft_id = ? WHERE id IN (?, ?)", (stale, old, doc))
    c.commit()
    code, body = api(manual, "post", "/rec/combine", json={"appt": a, "role": "doctor"})
    assert code == 200 and body["ids"] == [doc]
    assert wait_state(manual, doc, ["下書き", "失敗"])["state"] == "下書き"
    c = con_of(manual)
    assert c.execute("SELECT COUNT(*) FROM drafts WHERE body = '昔の要約'").fetchone()[0] == 0  # 古い要約は残らない
    o = recpipe.get(c, old)
    assert o["state"] == "文字起こし済み" and not o["draft_id"]  # 前の診療回の区切りは、消えた要約を指さない
    new = c.execute("SELECT transcript FROM drafts WHERE id = ?", (recpipe.get(c, doc)["draft_id"],)).fetchone()[0]
    assert OLD_TEXT not in new and TODAY_TEXT in new
    assert OLD_TEXT not in " ".join(u for _, u in mouth.sent)


def test_last_visit_answer_follows_visit_date_not_edit_order(manual):
    """あとで過去の回を直しても、「前回」は診療日が一番新しいメモ（直した順ではない）。"""
    c = con_of(manual)
    pid = c.execute("SELECT id FROM patients WHERE chart_no = '0123'").fetchone()[0]
    vid = c.execute("SELECT id FROM visits WHERE patient_id = ? LIMIT 1", (pid,)).fetchone()[0]
    latest = c.execute("SELECT MAX(note_date) FROM clinical_notes WHERE patient_id = ?", (pid,)).fetchone()[0]
    c.execute("INSERT INTO clinical_notes (patient_id, visit_id, note_date, author_role, body) VALUES (?, ?, '2026-01-05', 'doctor', ?)",
              (pid, vid, "あとから直した古い回"))
    c.commit()
    res = ask_mod.answer("前回は何をした？", c, pid, Gateway(mouth=ScriptedMouth("{}")))
    assert res["result"] == "found" and "あとから直した古い回" not in "".join(res["lines"])
    assert res["source"] == f"出どころ: {int(latest[:4])}年{int(latest[5:7])}月{int(latest[8:10])}日の診療記録"
