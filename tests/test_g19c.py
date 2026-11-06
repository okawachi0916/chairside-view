"""G19c: 録音の区切りを日付 × 役割で分ける。まとめて要約は今日の・今の役割の分だけ。確定した区切りは消せない。
本物の Claude と文字起こしは呼ばない（偽物）。"""
import json
from datetime import datetime, timedelta

import pytest

from app.ai import memo, recpipe
from app.ai.fake import ScriptedMouth
from tests.test_g19b import manual, reply_for  # noqa: F401
from tests.test_rec_pipeline import EMPTY, api, appt_of, con_of, env, use, wait_state  # noqa: F401

TODAY_TEXT = "今日は右下6番の根管充填をしました。"
OLD_TEXT = "前の日は根管の洗浄をしました。"
HYG_TEXT = "清掃の仕方をお伝えしました。"


def visit_day(c, vid):
    return c.execute("SELECT visit_date FROM visits WHERE id = ?", (vid,)).fetchone()[0]


def day_before(day, days):
    return (datetime.fromisoformat(day) - timedelta(days=days)).strftime("%Y-%m-%d")


def add_segment(env, appt, text, days=0, role="", state="文字起こし済み"):
    """区切りを直接入れる。days>0 は、その日数だけ前の診療回（前の診療日）の区切り（前の日の録音の代わり）。"""
    c = con_of(env)
    pid, vid = recpipe.visit_for(c, appt)
    day = day_before(visit_day(c, vid), days)
    if days:
        vid = c.execute("INSERT INTO visits (patient_id, visit_date, start_time, role, unit, status) VALUES (?, ?, '14:30', 'doctor', 2, 'closed')",
                        (pid, day)).lastrowid
    n = c.execute("SELECT COALESCE(MAX(rec_no), 0) + 1 FROM recordings").fetchone()[0]
    at = f"{datetime.now():%Y-%m-%d} 10:00:00"  # 録音した実際の時刻は、診療回の日付とは関係ない
    cur = c.execute("INSERT INTO recordings (rec_no, started_at, patient_id, visit_id, state, transcript, role, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (n, at, pid, vid, state, text, role, at))
    c.commit()
    return cur.lastrowid


def record_as(env, appt, role, text):
    env["mp"].setattr(recpipe.fake, "fake_transcript", lambda: text)
    code, r = api(env, "post", "/rec/start", json={"appt": appt, "role": role})
    assert code == 200
    assert api(env, "post", f"/rec/{r['id']}/audio?dur=30", content=b"RIFFfake-webm")[0] == 200
    assert api(env, "post", f"/rec/{r['id']}/transfer", json={})[0] == 200
    assert wait_state(env, r["id"], ["文字起こし済み", "失敗"])["state"] == "文字起こし済み"
    return r["id"]


def test_start_keeps_the_role_chosen_on_screen(manual):
    a = appt_of(manual, "0123")
    code, r = api(manual, "post", "/rec/start", json={"appt": a, "role": "hygienist"})
    assert code == 200 and r["role"] == "hygienist"
    code, r = api(manual, "post", "/rec/start", json={"appt": a})  # 渡されなければ空で、診療回の担当から決まる
    assert r["role"] == ""
    c = con_of(manual)
    assert recpipe.role_of(c, recpipe.get(c, r["id"])) == "doctor"  # この予約は歯科医師の担当


def test_role_without_record_falls_back_to_visit_then_doctor(manual):
    a = appt_of(manual, "0123")
    old = add_segment(manual, a, OLD_TEXT, days=1)
    c = con_of(manual)
    assert recpipe.role_of(c, recpipe.get(c, old)) == "doctor"
    c.execute("UPDATE visits SET role = '' WHERE appointment_id = ?", (a,))
    c.commit()
    assert recpipe.role_of(c, recpipe.get(c, old)) == "doctor"  # 決められなければ歯科医師


def test_combine_takes_only_todays_segments_of_the_chosen_role(manual):
    mouth = use(manual, ScriptedMouth(reply_for(("右下6番の根管充填。", "根管充填をしました"))), TODAY_TEXT)
    a = appt_of(manual, "0123")
    old = add_segment(manual, a, OLD_TEXT, days=1, role="doctor")
    hyg = record_as(manual, a, "hygienist", HYG_TEXT)
    doc = record_as(manual, a, "doctor", TODAY_TEXT)
    code, body = api(manual, "post", "/rec/combine", json={"appt": a, "role": "doctor"})
    assert code == 200 and body["ids"] == [doc]
    assert wait_state(manual, doc, ["下書き", "失敗"])["state"] == "下書き"
    c = con_of(manual)
    assert recpipe.get(c, old)["state"] == "文字起こし済み" and recpipe.get(c, hyg)["state"] == "文字起こし済み"
    sent = " ".join(u for _, u in mouth.sent)
    assert OLD_TEXT not in sent and HYG_TEXT not in sent  # 前の日・もう一方の役割は Claude に送っていない
    mouth.sent.clear()
    code, body = api(manual, "post", "/rec/combine", json={"appt": a, "role": "hygienist"})
    assert code == 200 and body["ids"] == [hyg]  # 衛生士は衛生士の分だけ


def test_combine_nothing_for_today_is_refused(manual):
    use(manual, ScriptedMouth(EMPTY), TODAY_TEXT)
    a = appt_of(manual, "0123")
    add_segment(manual, a, OLD_TEXT, days=1, role="doctor")
    code, body = api(manual, "post", "/rec/combine", json={"appt": a, "role": "doctor"})
    assert code == 409 and "ありません" in body["error"]


def test_screen_splits_by_date_and_role_today_first(manual):
    use(manual, ScriptedMouth(EMPTY), TODAY_TEXT)
    a = appt_of(manual, "0123")
    add_segment(manual, a, OLD_TEXT, days=1, role="doctor")
    add_segment(manual, a, HYG_TEXT, days=1, role="hygienist")
    add_segment(manual, a, OLD_TEXT, days=2, role="doctor")
    record_as(manual, a, "hygienist", HYG_TEXT)
    record_as(manual, a, "doctor", TODAY_TEXT)
    html = manual["client"].get(f"/api/view/unit?appt={a}&role=doctor").json()["html"]
    import re

    heads = re.findall(r'<h4 class="seg-day">([^<]*)</h4>', html)
    c = con_of(manual)
    today = segview_label(c, a, 0)
    assert heads[0] == f"{today} 歯科医師" and heads[1] == f"{today} 歯科衛生士"  # 今日が上、今の役割が先
    assert heads[2:4] == [f"{segview_label(c, a, 1)} 歯科医師", f"{segview_label(c, a, 1)} 歯科衛生士"]
    assert heads[4] == f"{segview_label(c, a, 2)} 歯科医師" and len(heads) >= 5  # さらに前の診療回の分は、さらに下（見本の10月の分はその下）
    assert html.count("data-today=1") == 2
    # 歯科衛生士で開くと、今の役割が変わる
    html2 = manual["client"].get(f"/api/view/unit?appt={a}&role=hygienist").json()["html"]
    assert re.findall(r'<h4 class="seg-day">([^<]*)</h4>', html2)[0] == f"{today} 歯科衛生士"


def segview_label(c, appt, days):
    from app.ai import segview

    today = visit_day(c, recpipe.visit_for(c, appt)[1])
    return segview.date_label(day_before(today, days), today)


def test_combine_button_only_when_todays_segments_of_this_role(manual):
    use(manual, ScriptedMouth(EMPTY), TODAY_TEXT)
    a = appt_of(manual, "0123")
    add_segment(manual, a, OLD_TEXT, days=1, role="doctor")
    page = lambda role: manual["client"].get(f"/api/view/unit?appt={a}&role={role}").json()["html"]  # noqa: E731
    assert 'data-seg="combine"' not in page("doctor")  # 前の日の分しか無いので出さない
    record_as(manual, a, "hygienist", HYG_TEXT)
    assert 'data-seg="combine"' in page("hygienist") and 'data-role="hygienist"' in page("hygienist")
    assert 'data-seg="combine"' not in page("doctor")  # 衛生士の分は歯科医師の画面ではまとめない


def test_confirmed_segment_has_no_delete_button_and_cannot_be_deleted(manual):
    use(manual, ScriptedMouth(EMPTY), TODAY_TEXT)
    a = appt_of(manual, "0123")
    done = add_segment(manual, a, OLD_TEXT, days=1, role="doctor", state="確定")
    open_ = add_segment(manual, a, TODAY_TEXT, days=0, role="doctor")
    html = manual["client"].get(f"/api/view/unit?appt={a}&role=doctor").json()["html"]
    assert f'data-seg="delete" data-id="{open_}"' in html
    assert f'data-seg="delete" data-id="{done}"' not in html
    code, body = api(manual, "post", f"/rec/{done}/delete")
    assert code == 409 and "確定" in body["error"] and "消せません" in body["error"]


def test_seed_sample_segments_are_dated_before_today():
    from app.db import initial
    from app.today import BASE  # 見本は BASE を「今日」として書いてある（今日へずらすのは dates.py）

    built = initial.build()
    rows = built["recordings"]
    visits = {v["id"]: v["visit_date"] for v in built["visits"]}
    assert rows and all(r["started_at"][:10] == visits[r["visit_id"]] < BASE for r in rows)  # 前の診療回の日付
    assert {r["role"] for r in rows} == {"doctor", "hygienist"} and all(r["state"] == "確定" for r in rows)
