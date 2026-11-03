"""G19: 下書きの確定と、後で直す仕組みの試験。本物の Claude と文字起こしは呼ばない（偽物）。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.ai import memo, recpipe
from app.ai.fake import ScriptedMouth
from tests.test_rec_pipeline import ROOT, api, appt_of, con_of, env, record, use, wait_state  # noqa: F401

TALK = "今日は右下6番の根管充填をしました。今後の治療計画は、右下6番は被せ物を入れます。"
REPLY = json.dumps({**{k: [] for k in memo.KEYS},
                    "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"}],
                    "future_plan": [{"text": "右下6番は被せ物を入れる", "quote": "右下6番は被せ物を入れます"}]}, ensure_ascii=False)


def make_draft(env, chart="0123", transcript=TALK, reply=REPLY):
    use(env, ScriptedMouth(reply), transcript)
    rid = record(env, appt_of(env, chart))
    assert api(env, "post", f"/rec/{rid}/transfer", json={})[0] == 200
    r = wait_state(env, rid, ["下書き", "失敗"])
    return rid, r


def items_of(env, draft_id):
    return api(env, "get", f"/api/drafts/{draft_id}")[1]


def counts(env):
    c = con_of(env)
    out = (c.execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0],
           c.execute("SELECT COUNT(*) FROM treatment_plans").fetchone()[0])
    c.close()
    return out


def plan_rows(env, chart="0123"):
    c = con_of(env)
    rows = [dict(r) for r in c.execute(
        "SELECT t.* FROM treatment_plans t JOIN patients p ON p.id = t.patient_id WHERE p.chart_no = ? AND t.kind = 'plan' "
        "ORDER BY t.seq, t.id", (chart,))]
    c.close()
    return rows


def test_nothing_enters_records_before_confirm(env):
    before = counts(env)
    plans = plan_rows(env)
    rid, r = make_draft(env)
    assert r["state"] == "下書き"
    assert counts(env) == before and plan_rows(env) == plans  # 診療メモにも治療計画にも入らない
    api(env, "put", f"/api/drafts/{r['draft_id']}/items", json={"items": items_of(env, r["draft_id"])["items"]})
    assert counts(env) == before


def test_edit_then_confirm_enters_clinical_note_and_removes_audio(env):
    rid, r = make_draft(env)
    d = items_of(env, r["draft_id"])
    d["items"]["done"][0]["text"] = "右下6番の根管充填（直しました）"
    d["items"]["explained"].append({"text": "違和感が出るかもしれない", "quote": ""})
    before = counts(env)
    audio = Path(env["dir"]) / "audio" / f"rec_{rid}.webm"
    assert audio.exists()
    code, res = api(env, "post", f"/api/drafts/{r['draft_id']}/confirm", json={"items": d["items"], "plan": {}})
    assert code == 200
    c = con_of(env)
    assert counts(env)[0] == before[0] + 1
    note = c.execute("SELECT * FROM clinical_notes ORDER BY id DESC LIMIT 1").fetchone()
    assert "直しました" in note["body"] and "違和感" in note["body"]
    dr = c.execute("SELECT * FROM drafts WHERE id = ?", (r["draft_id"],)).fetchone()
    assert dr["status"] == "confirmed" and dr["confirmed_at"]
    assert note["patient_id"] == dr["patient_id"] and note["visit_id"] == dr["visit_id"]
    assert recpipe.get(c, rid)["state"] == "確定" and not audio.exists()  # 確定したら音声を消す
    assert api(env, "post", f"/api/drafts/{r['draft_id']}/confirm", json={"items": d["items"]})[0] == 409  # 二重に入れない
    assert api(env, "put", f"/api/drafts/{r['draft_id']}/items", json={"items": d["items"]})[0] == 409


def test_confirm_rejects_empty_and_bad_shape(env):
    rid, r = make_draft(env)
    empty = {k: [] for k in memo.KEYS}
    assert api(env, "post", f"/api/drafts/{r['draft_id']}/confirm", json={"items": empty})[0] == 400
    assert api(env, "post", f"/api/drafts/{r['draft_id']}/confirm", json={"items": {"done": []}})[0] == 400
    assert counts(env)[0] == con_of(env).execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0]


def test_plan_only_chosen_changes_apply_and_untouched_teeth_remain(env):
    rid, r = make_draft(env)
    d = items_of(env, r["draft_id"])
    old = {p["body"]: p["id"] for p in d["plans"]}
    right6 = next(i for b, i in old.items() if "右下6番" in b)
    left7 = next(i for b, i in old.items() if "左下7番" in b)
    # 選ばなければ何も変わらない
    api(env, "post", f"/api/drafts/{r['draft_id']}/confirm", json={"items": d["items"], "plan": {}})
    assert [p["body"] for p in plan_rows(env) if p["superseded_on"] is None] == [p["body"] for p in d["plans"]]

    rid2, r2 = make_draft(env)
    d2 = items_of(env, r2["draft_id"])
    plan = {"changes": [{"old_id": right6, "text": "右下6番は被せ物を入れる"}], "adds": ["右上1番の経過観察"]}
    assert api(env, "post", f"/api/drafts/{r2['draft_id']}/confirm", json={"items": d2["items"], "plan": plan})[0] == 200
    rows = plan_rows(env)
    active = [p["body"] for p in rows if p["superseded_on"] is None]
    assert "右下6番は被せ物を入れる" in active and "右上1番の経過観察" in active
    assert any("左下7番" in b for b in active)  # 話に出ていない左下7番はそのまま残る
    l7 = next(p for p in rows if p["id"] == left7)
    assert l7["superseded_on"] is None and "左下7番" in l7["body"]
    o = next(p for p in rows if p["id"] == right6)
    assert o["superseded_on"] == "2026-11-06"  # 古い計画は日付を付けて残す


def test_delete_is_only_by_choice_and_archived(env):
    rid, r = make_draft(env)
    d = items_of(env, r["draft_id"])
    target = d["plans"][-1]["id"]
    assert api(env, "post", f"/api/drafts/{r['draft_id']}/confirm", json={"items": d["items"], "plan": {"deletes": [target]}})[0] == 200
    row = next(p for p in plan_rows(env) if p["id"] == target)
    assert row["superseded_on"] == "2026-11-06" and row["body"]  # 消さずに日付を付けて残る


def test_plan_choice_of_other_patients_plan_is_rejected(env):
    rid, r = make_draft(env)
    d = items_of(env, r["draft_id"])
    other = plan_rows(env, "0456")[0]["id"]
    before = counts(env)
    code, _ = api(env, "post", f"/api/drafts/{r['draft_id']}/confirm", json={"items": d["items"], "plan": {"deletes": [other]}})
    assert code == 400 and counts(env) == before  # 途中までは入らない
    assert items_of(env, r["draft_id"])["status"] == "draft"


# ---- 後で直す・追記必要 ----

def test_later_keeps_audio_and_draft_and_marks_today(env):
    rid, r = make_draft(env)
    assert api(env, "post", f"/rec/{rid}/later")[0] == 200
    c = con_of(env)
    assert recpipe.get(c, rid)["state"] == "後で直す"
    assert (Path(env["dir"]) / "audio" / f"rec_{rid}.webm").exists()  # 音声は残る
    assert c.execute("SELECT status FROM drafts WHERE id = ?", (r["draft_id"],)).fetchone()[0] == "draft"  # 下書きのまま
    rows = api(env, "get", "/api/today")[1]["rows"]
    marked = [x for x in rows if x["mark"]]
    assert [x["chart_no"] for x in marked] == ["0123"] and marked[0]["mark"] == "大川内先生 追記必要"
    d = items_of(env, r["draft_id"])
    assert api(env, "post", f"/api/drafts/{r['draft_id']}/confirm", json={"items": d["items"]})[0] == 200
    assert not [x for x in api(env, "get", "/api/today")[1]["rows"] if x["mark"]]  # 確定すると消える


def test_unconfirmed_draft_marks_today_even_if_moved_on(env):
    rid, r = make_draft(env, "0456")
    assert [x["chart_no"] for x in api(env, "get", "/api/today")[1]["rows"] if x["mark"]] == ["0456"]


def test_seeded_drafts_do_not_count(env):
    assert not [x for x in api(env, "get", "/api/today")[1]["rows"] if x["mark"]]
    assert api(env, "get", f"/api/pending-memo?appt={appt_of(env, '0123')}")[1]["memos"] == []


def test_pending_memo_for_leaving_patient(env):
    rid, r = make_draft(env)
    a = appt_of(env, "0123")
    memos = api(env, "get", f"/api/pending-memo?appt={a}")[1]["memos"]
    assert len(memos) == 1 and memos[0]["draft_id"] == r["draft_id"]
    assert api(env, "get", f"/api/pending-memo?appt={appt_of(env, '0456')}")[1]["memos"] == []  # 別の患者様には出ない
    assert api(env, "post", "/api/pending-memo/later", json={"appt": a})[1] == {"later": 1}
    assert recpipe.get(con_of(env), rid)["state"] == "後で直す"


def test_failed_recording_goes_to_later_then_redo_from_transcription_and_confirm(env):
    use(env, ScriptedMouth(REPLY), "")
    env["mp"].setattr(recpipe.fake, "fake_transcript", lambda: (_ for _ in ()).throw(RuntimeError("機械が動かない")))
    a = appt_of(env, "0123")
    rid = record(env, a)
    api(env, "post", f"/rec/{rid}/transfer", json={})
    r = wait_state(env, rid, ["失敗"])
    assert r["error"] and r["audio_file"] and r["visit_id"]  # 音声と診療回が残る
    # 次の患者様へ進む前に止まり、「後で直す」で進める。その場で話し直さない
    memos = api(env, "get", f"/api/pending-memo?appt={a}")[1]["memos"]
    assert memos[0]["state"] == "失敗" and memos[0]["draft_id"] is None
    assert api(env, "post", "/api/pending-memo/later", json={"appt": a})[0] == 200
    assert recpipe.get(con_of(env), rid)["state"] == "後で直す"
    assert [x["chart_no"] for x in api(env, "get", "/api/today")[1]["rows"] if x["mark"]] == ["0123"]
    # あとで、保存した音声から文字起こしからやり直す
    env["mp"].setattr(recpipe.fake, "fake_transcript", lambda: TALK)
    assert api(env, "post", f"/rec/{rid}/retry")[0] == 200
    r = wait_state(env, rid, ["下書き"])
    d = items_of(env, r["draft_id"])
    assert api(env, "post", f"/api/drafts/{r['draft_id']}/confirm", json={"items": d["items"]})[0] == 200
    assert not [x for x in api(env, "get", "/api/today")[1]["rows"] if x["mark"]]


def test_reorganize_after_fixing_transcript_gives_new_draft_to_review(env):
    rid, r = make_draft(env)
    api(env, "post", f"/rec/{rid}/later")
    new_talk = "今日は左下5番のレジン充填をしました。"
    new_reply = json.dumps({**{k: [] for k in memo.KEYS}, "done": [{"text": "左下5番のレジン充填", "quote": "左下5番のレジン充填をしました"}]})
    use(env, ScriptedMouth(new_reply), new_talk)
    before = counts(env)
    assert api(env, "post", f"/rec/{rid}/reorganize", json={"transcript": new_talk})[0] == 200
    r2 = wait_state(env, rid, ["下書き", "失敗"])
    assert r2["state"] == "下書き" and r2["draft_id"] == r["draft_id"]
    d = items_of(env, r["draft_id"])
    assert d["status"] == "draft" and d["transcript"] == new_talk and d["items"]["done"][0]["text"] == "左下5番のレジン充填。"
    assert counts(env) == before  # 人が見て確定するまで入らない
    assert api(env, "post", f"/rec/{rid}/reorganize", json={"transcript": " "})[0] == 400


def test_state_survives_restart(env):
    rid, r = make_draft(env)
    api(env, "post", f"/rec/{rid}/later")
    code = (
        "import json\n"
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "c = TestClient(app)\n"
        "t = c.get('/api/today').json()['rows']\n"
        "p = c.get('/api/pending-memo', params={'appt': %d}).json()['memos']\n"
        "print(json.dumps({'marks': [x['chart_no'] for x in t if x['mark']], 'pending': len(p)}))\n" % appt_of(env, "0123"))
    e = {**os.environ, "CV_DATA_DIR": str(env["dir"]), "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r)\n%s" % (str(ROOT), code)],
                         env=e, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert out.returncode == 0, out.stderr[-500:]
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res == {"marks": ["0123"], "pending": 1}  # 新しく起動したプロセスでも、印・下書きが残る
    assert (Path(env["dir"]) / "audio" / f"rec_{rid}.webm").exists()


def test_today_page_columns_and_masked_name(env):
    page = env["client"].get("/today").text
    for col in ("時間", "カルテ番号", "氏名", "処置", "状態"):
        assert col in page
    rows = api(env, "get", "/api/today")[1]["rows"]
    assert rows and all(set(x) >= {"time", "chart_no", "name", "treatment", "state", "mark"} for x in rows)
