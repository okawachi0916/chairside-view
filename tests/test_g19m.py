"""G19m: 記録したら、関係する画面が全部そろう。記録は1回、その日は取り消せる。偽物の口。
結果を見る試験: 記録したあと・取り消したあとの、データベースと画面の中身を読む。"""
import json
import re

import pytest

from app.ai import confirm, records, reflect
from app.ai.ask import answer
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from app.db import connect
from app.mockview import tooth_chart as TC
from app.views import data as D
from app.voice.interpret import interpret
from tests.test_confirm import make_draft
from tests.test_g19l import cands, history, tooth
from tests.test_rec_pipeline import api, appt_of, con_of, env  # noqa: F401

NEXT = "二週間後に土台の形成をする"
POLICY = "経過を見て被せ物を考える"
DONE = ["右下6番の根管充填", "左上3番のCR充填"]
ALL = ["46:根管充填", "23:CR充填", f"next:0:{NEXT}", f"policy:0:{POLICY}"]


def items_g(done=DONE, nxt=(NEXT,), policy=(POLICY,), plan=()):
    mk = lambda xs: [{"text": t, "quote": ""} for t in xs]  # noqa: E731
    return {"done": mk(done), "explained": [], "next_plan": mk(nxt), "future_plan": mk(plan), "future_policy": mk(policy)}


def confirm_api(env, draft_id, items, picks, plan=None):
    return api(env, "post", f"/api/drafts/{draft_id}/confirm", json={"items": items, "plan": plan or {}, "picks": picks})


def unit_html(env, chart="0123", role="doctor"):
    return api(env, "get", f"/api/view/unit?appt={appt_of(env, chart)}&role={role}")[1]["html"]


def patient_id(env, chart="0123"):
    c = con_of(env)
    r = c.execute("SELECT id FROM patients WHERE chart_no = ?", (chart,)).fetchone()[0]
    c.close()
    return r


TABLES = ("tooth_status", "tooth_status_history", "treatment_history", "treatment_plans", "clinical_notes", "appointments", "drafts")


def snapshot(env, chart="0123"):
    c = con_of(env)
    pid = patient_id(env, chart)
    out = {}
    for t in TABLES:
        rows = c.execute(f"SELECT * FROM {t} WHERE patient_id = ? ORDER BY id", (pid,)).fetchall()
        out[t] = [tuple(r) for r in rows]
    out["recordings_state"] = [tuple(r) for r in c.execute("SELECT id, state FROM recordings ORDER BY id")]
    c.close()
    return out


def main_line(html):
    return re.search(r'<div class="main">(.*?)</div>', html).group(1)


# ---- 記録したら全部そろう ----

def test_record_makes_every_screen_follow(env):
    rid, r = make_draft(env)
    d = r["draft_id"]
    a = appt_of(env, "0123")
    before = unit_html(env)
    assert main_line(before) == "右下6番 根管充填"                     # 記録する前は、予約の予定のまま
    assert TC.today_teeth(["右下6番 根管充填"]) == {46}
    code, res = confirm_api(env, d, items_g(), ALL)
    assert code == 200, res
    html = unit_html(env)
    # 今日の処置の大きな1行は、記録した「やったこと」
    assert main_line(html) == "右下6番の根管充填、左上3番のCR充填"
    # 歯の絵: 右下6番は根充済、左上3番はCR。今日の歯（右下6番・左上3番）に自院の四角は付けない
    assert 'data-tooth="46" data-crown="健全" data-root="根充済"' in html and 'data-tooth="23" data-crown="CR"' in html
    assert 'tc-box done" data-tooth="23"' not in html and 'tc-box done" data-tooth="46"' not in html
    # 治療歴: 一番上に今日の行（2つ）
    h = history(env, "0123")
    assert [(x["done_date"], x["site"], x["content"]) for x in h[:2]] == [("2026-11-06", "左上3番", "CR充填"), ("2026-11-06", "右下6番", "根管充填")]
    # 治療方針: 新しい方針と、古い方針（日付つき）が全画面にある
    assert POLICY in html and "前の治療方針" in html
    old = con_of(env).execute("SELECT body, superseded_on FROM treatment_plans WHERE kind = 'policy' AND superseded_on IS NOT NULL").fetchall()
    assert old and all(x["superseded_on"] == "2026-11-06" for x in old) and old[0]["body"] in html
    # 受付: 次回
    p = patient_id(env)
    rec = api(env, "get", f"/api/view/reception?patient={p}")[1]["html"]
    assert NEXT in rec
    # 「次回は？」は、次回の予定から（治療計画の1番目ではない）。Claude へは送らない
    c = con_of(env)
    out = answer("次回は？", c, p, Gateway(mouth=ScriptedMouth("{}"), log_dir=env["log"]))
    c.close()
    assert out["result"] == "found" and out["sends"] == 0 and out["lines"] == [NEXT] and out["part"] == "next-appointment"
    # 予約: 済み（予約一覧・受付の回数・最近の来院）
    c = con_of(env)
    assert c.execute("SELECT status FROM appointments WHERE id = ?", (a,)).fetchone()[0] == "done"
    c.close()
    listed = {x["id"]: x["status"] for x in D.today_list()}
    assert listed[a] == "done"


def test_appointment_list_shows_done_and_reception_counts(env):
    rid, r = make_draft(env)
    a, p = appt_of(env, "0123"), patient_id(env)
    n0 = D.reception_data(p)["appt_count"]
    page = env["client"].get("/clinic").text
    assert page.count("done-tag") == 0
    assert confirm_api(env, r["draft_id"], items_g(), [])[0] == 200
    page = env["client"].get("/clinic").text
    assert page.count("done-tag") == 1 and "済み" in page
    d = D.reception_data(p)
    assert d["appt_count"] == n0 + 1                       # 受付の回数
    assert d["recent"][0]["visit_date"] == "2026-11-06"    # 最近の来院（今日記録した分が入る）


# ---- 外したものは入らない・何も外さなければ全部入る ----

def test_candidates_cover_tooth_next_and_policy(env):
    rid, r = make_draft(env)
    c = api(env, "post", f"/api/drafts/{r['draft_id']}/candidates", json={"items": items_g()})[1]["candidates"]
    assert [x["key"] for x in c] == ALL
    assert [x["kind"] for x in c] == ["tooth", "tooth", "next", "policy"]
    nx = next(x for x in c if x["kind"] == "next")
    assert nx["after"] == NEXT and nx["before"] != "（なし）"      # 今の次回の予定 → 新しい


def test_unpicked_candidates_enter_nowhere(env):
    rid, r = make_draft(env)
    before = snapshot(env)
    code, res = confirm_api(env, r["draft_id"], items_g(), [])
    assert code == 200, res
    after = snapshot(env)
    for t in ("tooth_status", "tooth_status_history", "treatment_history", "treatment_plans"):
        assert after[t] == before[t], t
    assert len(after["clinical_notes"]) == len(before["clinical_notes"]) + 1


def test_only_the_picked_next_goes_in_and_policy_stays(env):
    rid, r = make_draft(env)
    c0 = con_of(env)
    pol0 = [tuple(x) for x in c0.execute("SELECT * FROM treatment_plans WHERE kind = 'policy'")]
    c0.close()
    assert confirm_api(env, r["draft_id"], items_g(), [f"next:0:{NEXT}"])[0] == 200
    c = con_of(env)
    assert [tuple(x) for x in c.execute("SELECT * FROM treatment_plans WHERE kind = 'policy'")] == pol0
    assert [x["body"] for x in c.execute("SELECT body FROM treatment_plans WHERE kind = 'next' AND superseded_on IS NULL AND patient_id = ?", (patient_id(env),))] == [NEXT]
    c.close()


def test_stale_or_unknown_pick_is_refused_and_nothing_is_written(env):
    rid, r = make_draft(env)
    before = snapshot(env)
    code, res = confirm_api(env, r["draft_id"], items_g(), [f"next:0:{NEXT}x"])
    assert code >= 400 and "候補に無い" in res["error"]
    assert snapshot(env) == before


def test_plan_change_inherits_the_old_order(env):
    rid, r = make_draft(env)
    c = con_of(env)
    plans = [dict(x) for x in c.execute("SELECT id, seq, body FROM treatment_plans WHERE patient_id = ? AND kind = 'plan' AND superseded_on IS NULL ORDER BY seq, id", (patient_id(env),))]
    c.close()
    target = plans[0]
    code, res = confirm_api(env, r["draft_id"], items_g(), [], plan={"changes": [{"old_id": target["id"], "text": "新しい計画です"}]})
    assert code == 200, res
    c = con_of(env)
    now = [x["body"] for x in c.execute("SELECT body FROM treatment_plans WHERE patient_id = ? AND kind = 'plan' AND superseded_on IS NULL ORDER BY seq, id", (patient_id(env),))]
    c.close()
    assert now[0] == "新しい計画です" and now[1:] == [p["body"] for p in plans[1:]]   # 一番後ろに付けない


# ---- 取り消し ----

def test_cancel_restores_everything_then_record_again_is_not_doubled(env):
    rid, r = make_draft(env)
    d = r["draft_id"]
    before = snapshot(env)
    code, res = confirm_api(env, d, items_g(), ALL)
    assert code == 200, res
    done = snapshot(env)
    assert done != before
    code, res = api(env, "post", f"/api/drafts/{d}/cancel")
    assert code == 200 and res["draft_id"] == d and res["changes"] > 5, res
    assert snapshot(env) == before                                    # 診療メモ・計画・歯・治療歴・次回・方針・予約・下書きが全部戻る
    c = con_of(env)
    assert c.execute("SELECT COUNT(*) FROM record_changes").fetchone()[0] == 0
    c.close()
    assert tooth(env, "0123", 46)["root"] == "根治中" and main_line(unit_html(env)) == "右下6番 根管充填"
    assert api(env, "get", f"/api/drafts/{d}")[1]["status"] == "draft"
    # もう一度記録 → 1回目と同じ内容（二重にならない）
    assert confirm_api(env, d, items_g(), ALL)[0] == 200
    again = snapshot(env)
    assert len(again["treatment_history"]) == len(done["treatment_history"]) and len(again["clinical_notes"]) == len(done["clinical_notes"])
    assert len(again["tooth_status_history"]) == len(done["tooth_status_history"]) and len(again["treatment_plans"]) == len(done["treatment_plans"])


def test_cancel_by_appt_returns_the_draft(env):
    rid, r = make_draft(env)
    assert confirm_api(env, r["draft_id"], items_g(), ALL)[0] == 200
    code, res = api(env, "post", "/api/records/cancel", json={"appt": appt_of(env, "0123")})
    assert code == 200 and res["draft_id"] == r["draft_id"]
    code, res = api(env, "post", "/api/records/cancel", json={"appt": appt_of(env, "0123")})
    assert code == 409 and "取り消せる記録がありません" in res["error"]


def test_cannot_cancel_the_next_day(env, monkeypatch):
    from app.db import dates

    rid, r = make_draft(env)
    assert confirm_api(env, r["draft_id"], items_g(), ALL)[0] == 200
    monkeypatch.setenv("CV_TODAY", "2026-11-07")
    dates.forget()
    code, res = api(env, "post", f"/api/drafts/{r['draft_id']}/cancel")
    assert code == 409 and res["error"] == confirm.NOT_TODAY == "その日のうちだけ取り消せます"
    assert tooth(env, "0123", 46)["root"] == "根充済"                     # 何も戻っていない
    dates.forget()


def test_cancel_needs_the_later_record_cancelled_first(env):
    rid, r = make_draft(env)
    assert confirm_api(env, r["draft_id"], items_g(), ALL)[0] == 200
    rid2, r2 = make_draft(env)  # 同じ患者様の2つ目の記録（別の録音）
    assert confirm_api(env, r2["draft_id"], items_g(done=["右上5番のインレー装着"], nxt=(), policy=()), ["15:インレー装着"])[0] == 200
    code, res = api(env, "post", f"/api/drafts/{r['draft_id']}/cancel")
    assert code == 409 and "あとの記録" in res["error"]
    assert api(env, "post", f"/api/drafts/{r2['draft_id']}/cancel")[0] == 200
    assert api(env, "post", f"/api/drafts/{r['draft_id']}/cancel")[0] == 200


def test_one_failure_stops_the_whole_record(env, monkeypatch):
    from app.ai import journal

    rid, r = make_draft(env)
    before = snapshot(env)
    orig = journal.Journal.update

    def boom(self, tbl, row_id, **cols):
        if tbl == "appointments":
            raise RuntimeError("予約が書けません")
        return orig(self, tbl, row_id, **cols)

    monkeypatch.setattr(journal.Journal, "update", boom)
    with pytest.raises(RuntimeError):
        env["client"].post(f"/api/drafts/{r['draft_id']}/confirm", json={"items": items_g(), "plan": {}, "picks": ALL})
    assert snapshot(env) == before
    c = con_of(env)
    assert c.execute("SELECT COUNT(*) FROM record_changes").fetchone()[0] == 0
    c.close()


def test_undo_stops_whole_if_a_changed_row_is_gone(env):
    rid, r = make_draft(env)
    assert confirm_api(env, r["draft_id"], items_g(), ALL)[0] == 200
    c = con_of(env)
    c.execute("DELETE FROM treatment_history WHERE content = 'CR充填'")
    c.commit()
    c.close()
    snap = snapshot(env)
    code, res = api(env, "post", f"/api/drafts/{r['draft_id']}/cancel")
    assert code == 409 and "戻せませんでした" in res["error"]
    assert snapshot(env) == snap                                       # 途中まで戻した所も無い


# ---- 声 ----

def test_voice_words():
    assert interpret("カルテに記録する", "draft")["action"] == "draft-confirm"
    assert interpret("記録", "draft")["action"] == "draft-confirm"
    assert interpret("確定する", "draft")["action"] == "draft-confirm"
    assert interpret("3番 外す", "draft")["action"] == "draft-off" and interpret("3番 外す", "draft")["numbers"] == [3]
    assert interpret("3番を外して", "draft")["action"] == "draft-off"
    assert interpret("3番 付ける", "draft")["action"] == "draft-on"
    assert interpret("記録を取り消す", "unit")["action"] == "record-cancel"
    assert interpret("記録を取り消して", "unit")["action"] == "record-cancel"
    assert interpret("記録を取り消す", "draft")["action"] is None                       # 下書きの画面の言葉ではない
    from app.voice.interpret import load_table

    assert not [r for r in load_table() if r["結果"].get("action") == "draft-arm"]       # 2回言う決まりは無い


# ---- AI の答えに歯周検査の数字 ----

def test_perio_numbers_are_in_the_records_as_the_screen_shows_them(env):
    c = con_of(env)
    p = patient_id(env)
    recs = records.build_records(c, p)
    ex = D._perio(c, p, 1)[0]                                   # 歯科衛生士の画面と同じ計算
    line = next(x for x in recs if x.ref == f"perio:{ex['date']}")
    text = "\n".join(line.lines)
    assert f"出血（BOP）: {ex['bop']}%" in text and f"PCR: {ex['pcr']}%" in text
    deep = sorted(t for t, v in ex["teeth"].items() if v["pocket"] >= 4)
    assert text.count("mm") == len(deep) + 1 and f"（{len(deep)}本）" in text
    for t in deep:
        assert f"{ex['teeth'][t]['pocket']}mm" in text
    loose = [t for t, v in ex["teeth"].items() if v["mobility"] > 0]
    assert (f"（{len(loose)}本）" in text) if loose else ("動揺のある歯: なし（0本）" in text)
    # 古い検査には数字の行を足さない（新しい検査だけ）
    olds = [x for x in recs if x.part == "perio-exam" and x.ref != line.ref]
    assert all("BOP" not in "".join(o.lines) for o in olds)
    # 「4ミリ以上の歯は？」「出血は何％？」: Claude が選んだ番号の記録（この行）を、そのまま答えに出す
    for q in ("4ミリ以上の歯は？", "出血は何％？"):
        out = answer(q, c, p, Gateway(mouth=ScriptedMouth(json.dumps({"result": "found", "record": line.number})), log_dir=env["log"]))
        assert out["result"] == "found" and out["lines"] == line.lines and out["part"] == "perio-exam"
    c.close()


def test_policy_and_next_are_in_the_records(env):
    rid, r = make_draft(env)
    assert confirm_api(env, r["draft_id"], items_g(), ALL)[0] == 200
    c = con_of(env)
    recs = records.build_records(c, patient_id(env))
    c.close()
    assert [x.lines for x in recs if x.ref == "next:1"] == [[NEXT]] and [x.lines for x in recs if x.ref.startswith("policy:")] == [[POLICY]]
    # 同じ日の診療メモと治療歴は二重にならない（G19l）
    refs = [x.ref for x in recs]
    assert refs.count("note:2026-11-06") == 1 and "history:2026-11-06" not in refs


# ---- メンテナンスの前回 ----

def test_maintenance_last_is_the_last_hygienist_visit(env):
    p = patient_id(env)
    c = con_of(env)
    c.execute("UPDATE maintenance_intervals SET last_date = '2000-01-01' WHERE patient_id = ?", (p,))  # 保存した値は読まない
    c.commit()
    last = c.execute("SELECT MAX(visit_date) FROM visits WHERE patient_id = ? AND role = 'hygienist' AND visit_date < '2026-11-06'", (p,)).fetchone()[0]
    c.close()
    assert last
    html = unit_html(env, "0123", "hygienist")
    iv = D.unit_data(D.appointment(appt_of(env, "0123")), "hygienist")["interval"]
    assert iv["last_date"] == last and D.ja_date(last) in html and "2000年" not in html


def test_maintenance_last_falls_back_to_the_last_perio_exam(env):
    p = patient_id(env)
    c = con_of(env)
    c.execute("UPDATE visits SET role = 'doctor' WHERE patient_id = ? AND role = 'hygienist'", (p,))  # 歯科衛生士の診療回が1つも無い患者様
    c.commit()
    exam = c.execute("SELECT MAX(exam_date) FROM perio_exams WHERE patient_id = ? AND exam_date < '2026-11-06'", (p,)).fetchone()[0]
    left = c.execute("SELECT MAX(visit_date) FROM visits WHERE patient_id = ? AND role = 'hygienist' AND visit_date < '2026-11-06'", (p,)).fetchone()[0]
    c.close()
    iv = D.unit_data(D.appointment(appt_of(env, "0123")), "hygienist")["interval"]
    assert left is None and exam and iv["last_date"] == exam
