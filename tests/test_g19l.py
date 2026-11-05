"""G19l: 「カルテに記録する」で確定した治療を、歯の絵と治療歴にも反映する。偽物の口。
結果を見る試験: 確定したあとの歯の状態・治療歴・歯科医師の画面を、データベースと画面から読む。"""
import json
import os
import subprocess
import sys
from datetime import date, timedelta

import pytest

from app.ai import records, toothtx
from app.ai.fake import ScriptedMouth
from app.db import connect, dates
from app.mockview import tooth_chart as TC
from app.views import data as D
from tests.test_confirm import make_draft
from tests.test_rec_pipeline import ROOT, api, appt_of, con_of, env  # noqa: F401


def items_with(*rows):
    base = {k: [] for k in ("done", "explained", "next_plan", "future_plan", "future_policy")}
    base["done"] = [{"text": t, "quote": ""} for t in rows]
    return base


def cands(env, draft_id, *rows):
    code, d = api(env, "post", f"/api/drafts/{draft_id}/tooth-candidates", json={"items": items_with(*rows)})
    assert code == 200, d
    return d["candidates"]


def tooth(env, chart, t):
    c = con_of(env)
    r = c.execute("SELECT s.* FROM tooth_status s JOIN patients p ON p.id = s.patient_id WHERE p.chart_no = ? AND s.tooth = ?", (chart, t)).fetchone()
    c.close()
    return dict(r) if r else None


def history(env, chart):
    c = con_of(env)
    rows = [dict(r) for r in c.execute(
        "SELECT h.* FROM treatment_history h JOIN patients p ON p.id = h.patient_id WHERE p.chart_no = ? "
        "ORDER BY h.done_date DESC, h.id DESC", (chart,))]
    c.close()
    return rows


def snapshot(env, chart="0123"):
    c = con_of(env)
    pid = c.execute("SELECT id FROM patients WHERE chart_no = ?", (chart,)).fetchone()[0]
    snap = {t: [tuple(r) for r in c.execute(f"SELECT * FROM {t} WHERE patient_id = ? ORDER BY id", (pid,))]
            for t in ("tooth_status", "tooth_status_history", "treatment_history", "clinical_notes", "treatment_plans")}
    c.close()
    return snap


def confirm(env, draft_id, items, teeth, plan=None):
    return api(env, "post", f"/api/drafts/{draft_id}/confirm", json={"items": items, "plan": plan or {}, "teeth": teeth})


def unit_html(env, chart="0123"):
    a = appt_of(env, chart)
    return api(env, "get", f"/api/view/unit?appt={a}&role=doctor")[1]["html"]


# ---- 候補 ----

def test_candidate_from_done_row_with_one_tooth_and_known_word(env):
    rid, r = make_draft(env)
    c = cands(env, r["draft_id"], "右下6番の根管充填")
    assert [(x["key"], x["site"], x["word"]) for x in c] == [("46:根管充填", "右下6番", "根管充填")]
    assert c[0]["before"] == "健全、根治中" and c[0]["after"] == "健全、根充済"  # 今 → 記録後


def test_unknown_words_and_undecided_sites_are_not_candidates(env):
    rid, r = make_draft(env)
    d = r["draft_id"]
    assert cands(env, d, "右下6番の歯石除去") == []                      # 表に無い言葉
    assert cands(env, d, "根管充填をした") == []                         # 歯が決まらない
    assert cands(env, d, "下顎の抜歯") == []                             # 顎は1本に決まらない
    assert cands(env, d, "全顎のCR充填") == []
    assert cands(env, d, "右下6番と右下7番の根管充填") == []             # 2本の話は、どちらか決められない
    assert cands(env, d, "下顎 右下6番の根管充填") == []                 # 部位の言葉が2つ
    assert [x["key"] for x in cands(env, d, "歯石除去", "右下6番の根管充填", "全顎のSPT")] == ["46:根管充填"]


def test_every_word_in_the_table_gives_its_state(env):
    rid, r = make_draft(env)
    d = r["draft_id"]
    got = {x["word"]: x for x in cands(env, d, "左上3番の抜歯", "左上4番のCR充填", "左上5番のインレー装着", "左上6番のクラウン装着",
                                       "左上7番の抜髄", "左上2番の感染根管治療", "左上1番の根管貼薬", "右上3番のインプラント埋入", "左下2番の根管充填")}
    assert set(got) == {t["label"] for t in toothtx.load_table()}  # 表の処置が全部、候補に出る
    assert got["根管充填"]["after"] == "健全、根充済" and got["抜歯"]["after"] == "欠損" and got["抜髄"]["after"] == "健全、根治中"
    assert got["CR充填"]["after"] == "CR" and got["クラウン装着"]["after"].startswith("クラウン")
    assert got["インプラント埋入"]["after"] == "インプラント（上部構造なし）"


def test_longer_word_wins_and_is_not_counted_twice(env):
    rid, r = make_draft(env)
    c = cands(env, r["draft_id"], "右下6番は感染根管治療と根管充填")
    assert sorted(x["word"] for x in c) == ["感染根管治療", "根管充填"]
    c = cands(env, r["draft_id"], "右下6番の根管充填、根管充填")
    assert [x["key"] for x in c] == ["46:根管充填"]


def test_table_words_are_valid_for_the_chart(env):
    for t in toothtx.load_table():
        assert not t["set"].get("crown") or t["set"]["crown"] in TC.CROWNS
        assert not t["set"].get("root") or t["set"]["root"] in TC.ROOTS_STATE


# ---- 確定 ----

def test_confirm_writes_tooth_state_history_and_keeps_the_old_state(env):
    rid, r = make_draft(env)
    before = tooth(env, "0123", 46)
    assert (before["crown"], before["root"]) == ("健全", "根治中")  # 見本の右下6番は根の治療中
    hist = history(env, "0123")
    items = api(env, "get", f"/api/drafts/{r['draft_id']}")[1]["items"]
    code, d = confirm(env, r["draft_id"], items, ["46:根管充填"])
    assert code == 200, d
    after = tooth(env, "0123", 46)
    assert after["root"] == "根充済" and after["crown"] == "健全" and "根充済" in after["status"]
    # 治療歴: 一番上に今日（診療回の日）の行
    h = history(env, "0123")
    assert len(h) == len(hist) + 1
    assert h[0]["done_date"] == "2026-11-06" and h[0]["site"] == "右下6番" and h[0]["content"] == "根管充填"
    # 古い状態は日付を付けて残る
    c = con_of(env)
    old = c.execute("SELECT * FROM tooth_status_history").fetchall()
    c.close()
    assert len(old) == 1 and (old[0]["tooth"], old[0]["crown"], old[0]["root"], old[0]["superseded_on"]) == (46, "健全", "根治中", "2026-11-06")
    # 歯科医師の画面: 右下6番が根充済の描き方、治療歴の一番上に今日の行
    html = unit_html(env)
    assert 'data-tooth="46" data-crown="健全" data-root="根充済"' in html
    hist_html = html[html.index("<th>日付</th><th>部位</th><th>内容</th>"):]  # 歯科医師の画面の治療歴の表
    first = hist_html[hist_html.index("<tbody>"):hist_html.index("</tr>", hist_html.index("<tbody>"))]
    assert "2026/11/6" in first and "右下6番" in first and "根管充填" in first
    # 自院の印（自院で治療済みの歯の判定）
    c = con_of(env)
    appt = dict(c.execute("SELECT * FROM appointments WHERE id = ?", (appt_of(env, "0123"),)).fetchone())
    c.close()
    d_ = D.unit_data(appt, "doctor")
    assert 46 in TC.own_teeth(d_["teeth"], [x["site"] for x in d_["history"]], d_["dentures"])


def test_new_tooth_without_history_becomes_own_and_cr_clears_caries(env):
    rid, r = make_draft(env)
    assert tooth(env, "0123", 15)["caries"] == 1  # 見本の右上5番はカリエス
    items = items_with("右上5番のCR充填")
    code, d = confirm(env, r["draft_id"], items, ["15:CR充填"])
    assert code == 200, d
    t = tooth(env, "0123", 15)
    assert (t["crown"], t["caries"]) == ("CR", 0)
    assert history(env, "0123")[0]["site"] == "右上5番"
    html = unit_html(env)
    assert 'data-tooth="15" data-crown="CR" data-root="生活" data-caries="0"' in html


def test_extraction_marks_missing_and_a_tooth_without_a_row_gets_a_row(env):
    rid, r = make_draft(env)
    assert tooth(env, "0123", 31) is None  # 状態の行が無い歯（健全）
    code, d = confirm(env, r["draft_id"], items_with("左下1番の抜歯", "左下2番のCR充填"), ["31:抜歯", "32:CR充填"])
    assert code == 200, d
    assert tooth(env, "0123", 31)["status"] == "欠損" and tooth(env, "0123", 31)["crown"] == "欠損"
    assert tooth(env, "0123", 32)["crown"] == "CR"
    c = con_of(env)
    assert c.execute("SELECT COUNT(*) FROM tooth_status_history WHERE tooth IN (31, 32)").fetchone()[0] == 0  # 前の行が無いので、残す古い状態も無い
    c.close()


def test_unpicked_candidates_change_nothing(env):
    rid, r = make_draft(env)
    snap = snapshot(env)
    items = api(env, "get", f"/api/drafts/{r['draft_id']}")[1]["items"]
    assert cands(env, r["draft_id"], "右下6番の根管充填")  # 候補はある
    code, d = confirm(env, r["draft_id"], items, [])
    assert code == 200, d
    after = snapshot(env)
    assert after["tooth_status"] == snap["tooth_status"] and after["tooth_status_history"] == snap["tooth_status_history"]
    assert after["treatment_history"] == snap["treatment_history"]
    assert len(after["clinical_notes"]) == len(snap["clinical_notes"]) + 1  # 診療メモは入る


def test_only_the_picked_one_is_written(env):
    rid, r = make_draft(env)
    items = items_with("右下6番の根管充填", "左上5番のCR充填")
    code, d = confirm(env, r["draft_id"], items, ["25:CR充填"])
    assert code == 200, d
    assert tooth(env, "0123", 46)["root"] == "根治中" and tooth(env, "0123", 25)["crown"] == "CR"
    assert [x["site"] for x in history(env, "0123")[:1]] == ["左上5番"]


# ---- 失敗は確定ごと止める ----

@pytest.mark.parametrize("teeth,word", [(["46:抜歯"], "候補に無い"), (["46:根管充填", "46:根管充填"], "正しくありません")])
def test_bad_pick_stops_the_whole_confirm(env, teeth, word):
    rid, r = make_draft(env)
    snap = snapshot(env)
    items = api(env, "get", f"/api/drafts/{r['draft_id']}")[1]["items"]
    code, d = confirm(env, r["draft_id"], items, teeth)
    assert code >= 400 and word in d["error"], d
    assert snapshot(env) == snap  # 診療メモにも治療計画にも入らない
    assert api(env, "get", f"/api/drafts/{r['draft_id']}")[1]["status"] == "draft"


def test_two_treatments_on_the_same_part_of_a_tooth_are_refused(env):
    rid, r = make_draft(env)
    snap = snapshot(env)
    code, d = confirm(env, r["draft_id"], items_with("右下6番は抜髄と根管充填"), ["46:抜髄", "46:根管充填"])
    assert code == 409 or code == 400
    assert "両方が選ばれています" in d["error"] and snapshot(env) == snap


def test_write_failure_rolls_back_note_and_plans(env, monkeypatch):
    rid, r = make_draft(env)
    snap = snapshot(env)
    items = api(env, "get", f"/api/drafts/{r['draft_id']}")[1]["items"]

    def broken(con, *a, **k):
        con.execute("INSERT INTO tooth_status_history (patient_id, tooth, superseded_on) VALUES (1, 46, '2026-11-06')")  # 半分書いてから失敗
        raise RuntimeError("書けません")

    monkeypatch.setattr(toothtx, "apply", broken)
    with pytest.raises(RuntimeError):
        env["client"].post(f"/api/drafts/{r['draft_id']}/confirm", json={"items": items, "plan": {}, "teeth": ["46:根管充填"]})
    assert snapshot(env) == snap


# ---- AI の記録の番号が二重にならない ----

def test_history_and_note_of_the_same_day_are_one_record_for_the_ai(env):
    rid, r = make_draft(env)
    items = api(env, "get", f"/api/drafts/{r['draft_id']}")[1]["items"]
    assert confirm(env, r["draft_id"], items, ["46:根管充填"])[0] == 200
    c = con_of(env)
    pid = c.execute("SELECT id FROM patients WHERE chart_no = '0123'").fetchone()[0]
    recs = records.build_records(c, pid)
    c.close()
    assert [x.ref for x in recs].count("note:2026-11-06") == 1
    assert "history:2026-11-06" not in [x.ref for x in recs]  # 今日の治療歴は、同じ日の診療メモがあるので番号を付けない


# ---- 日付と見本の状態へ戻す ----

def test_dates_of_added_rows_move_with_the_sample(env, monkeypatch):
    rid, r = make_draft(env)
    items = api(env, "get", f"/api/drafts/{r['draft_id']}")[1]["items"]
    assert confirm(env, r["draft_id"], items, ["46:根管充填"])[0] == 200
    assert dates.SHIFT["tooth_status_history"] == ["superseded_on"]
    monkeypatch.setenv("CV_TODAY", "2026-11-09")
    dates.forget()
    con = connect()  # 開くときに今日へ合わせる
    h = con.execute("SELECT done_date FROM treatment_history WHERE site = '右下6番' AND content = '根管充填'").fetchone()[0]
    s = con.execute("SELECT superseded_on FROM tooth_status_history").fetchone()[0]
    n = con.execute("SELECT note_date FROM clinical_notes ORDER BY id DESC LIMIT 1").fetchone()[0]
    con.close()
    assert h == s == n == "2026-11-09"  # 診療メモと同じだけ動く
    dates.forget()


def test_demo_restore_brings_back_tooth_and_history(env, tmp_path):
    e = {**os.environ, "CV_DEMO_DIR": str(tmp_path / "demo"), "PYTHONIOENCODING": "utf-8"}
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "scripts" / "demo_state.py"), *a], env=e, capture_output=True, text=True, encoding="utf-8")  # noqa: E731
    assert run("save", "前").returncode == 0
    rid, r = make_draft(env)
    items = api(env, "get", f"/api/drafts/{r['draft_id']}")[1]["items"]
    assert confirm(env, r["draft_id"], items, ["46:根管充填"])[0] == 200
    assert tooth(env, "0123", 46)["root"] == "根充済"
    p = run("restore", "前")
    assert p.returncode == 0, p.stderr
    assert tooth(env, "0123", 46)["root"] == "根治中"   # 右下6番が根の治療中に戻る
    assert not [x for x in history(env, "0123") if x["content"] == "根管充填" and x["done_date"] == "2026-11-06"]  # 今日の治療歴の行が消える
    c = con_of(env)
    assert c.execute("SELECT COUNT(*) FROM tooth_status_history").fetchone()[0] == 0
    c.close()


def test_update_db_adds_the_new_table_to_an_old_database_and_keeps_data(env):
    from app.db import schema

    c = connect()
    c.execute("DROP TABLE tooth_status_history")
    c.commit()
    c.close()
    n = len(history(env, "0123"))
    assert subprocess.run([sys.executable, str(ROOT / "scripts" / "update_db.py")], env={**os.environ}, capture_output=True).returncode == 0
    c = connect()
    assert c.execute("SELECT COUNT(*) FROM tooth_status_history").fetchone()[0] == 0   # 表ができている
    c.close()
    assert len(history(env, "0123")) == n and "tooth_status_history" in schema.TABLES
