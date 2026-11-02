"""G17: 録音から下書きまでの流れの試験。本物の Claude と文字起こしは呼ばない（偽物）。"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import memo, recpipe
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from tests.memo_eval import CASES, judge

ROOT = Path(__file__).resolve().parents[1]
EMPTY = json.dumps({k: [] for k in memo.KEYS})


@pytest.fixture
def env(tmp_path, monkeypatch):
    """作り直した架空データ。録音の音声もこの中に置く。"""
    d = tmp_path / "data"
    d.mkdir()
    e = {**os.environ, "CV_DATA_DIR": str(d), "PYTHONIOENCODING": "utf-8"}
    assert subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], env=e, capture_output=True).returncode == 0
    monkeypatch.setenv("CV_DATA_DIR", str(d))
    monkeypatch.setenv("CHAIRSIDE_AI_TIMEOUT", "30")
    monkeypatch.setattr(recpipe.fake, "fake_transcript", lambda: "")  # 既定: 空 (各試験で差し替える)
    recpipe._live.clear()
    from app.main import app

    return {"client": TestClient(app), "dir": d, "mp": monkeypatch, "log": tmp_path / "log"}


def use(env, mouth, transcript="今日は右下6番の根管充填をしました。次回は二週間後に土台を立てます。"):
    import app.routers.ai as router

    env["mp"].setattr(router, "make_gateway", lambda: Gateway(mouth=mouth, log_dir=env["log"]))
    env["mp"].setattr(recpipe.fake, "fake_transcript", lambda: transcript)
    return mouth


def con_of(env):
    from app.db import connect

    return connect()


def appt_of(env, chart):
    c = con_of(env)
    r = c.execute("SELECT a.id FROM appointments a JOIN patients p ON p.id = a.patient_id WHERE p.chart_no = ? "
                  "AND a.appt_date = '2026-11-06' AND a.status = 'booked' ORDER BY a.start_time", (chart,)).fetchone()
    c.close()
    return r[0]


def wait_state(env, rec_id, states, sec=10):
    t0 = time.time()
    while time.time() - t0 < sec:
        c = con_of(env)
        r = recpipe.get(c, rec_id)
        c.close()
        if r["state"] in states:
            return r
        time.sleep(0.05)
    raise AssertionError(f"状態が {states} にならない: {r['state']} {r['error']}")


def api(env, method, url, **kw):
    r = getattr(env["client"], method)(url, **kw)
    return r.status_code, r.json()


def record(env, appt=None, audio=b"RIFFfake-webm"):
    code, r = api(env, "post", "/rec/start", json={"appt": appt})
    assert code == 200
    code, r2 = api(env, "post", f"/rec/{r['id']}/audio?dur=84", content=audio)
    assert code == 200
    return r["id"]


# ---- 5つに分ける ----

def test_states_are_the_eight():
    assert recpipe.STATES == ["録音中", "転送待ち", "文字起こし中", "整理中", "失敗", "下書き", "確定", "後で直す"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"case{c['id']}")
def test_six_cases_with_fake_mouth(case):
    items = memo.parse_items(json.dumps(case["fake_reply"], ensure_ascii=False), case["transcript"])
    assert judge(items, case["expect"]) == [], case["title"]
    for k in memo.KEYS:  # 抜き出しは全部、話した文字の中にある
        for r in items[k]:
            assert memo._squash(r["quote"]) in memo._squash(case["transcript"])


def test_lines_without_real_quote_are_dropped():
    spoken = "今日は根管充填をしました。"
    reply = json.dumps({**{k: [] for k in memo.KEYS}, "done": [
        {"text": "根管充填", "quote": "根管充填をしました"},
        {"text": "抜歯", "quote": "抜歯をしました"},         # 話していない
        {"text": "投薬", "quote": ""},                        # 抜き出しが空
    ]})
    items = memo.parse_items(reply, spoken)
    assert [r["text"] for r in items["done"]] == ["根管充填"]


@pytest.mark.parametrize("raw", ["", "文章です", "[]", '{"done":[]}', '{"done":[],"explained":[],"next_plan":[],'
                                 '"future_plan":[],"future_policy":[],"extra":[]}',
                                 '{"done":"x","explained":[],"next_plan":[],"future_plan":[],"future_policy":[]}',
                                 '{"done":[{"text":"a"}],"explained":[],"next_plan":[],"future_plan":[],"future_policy":[]}'])
def test_wrong_shape_is_rejected(raw):
    with pytest.raises(ValueError):
        memo.parse_items(raw, "あ")


def test_names_do_not_reach_claude(env):
    sent = use(env, ScriptedMouth(EMPTY), "見本 花子さん、今日は根管充填をしました。ハナコさんにも説明しました。")
    rid = record(env, appt_of(env, "0123"))
    api(env, "post", f"/rec/{rid}/transfer", json={})
    r = wait_state(env, rid, ["下書き", "失敗"])
    assert r["state"] == "下書き", r["error"]
    system, user = sent.sent[0]
    assert "見本" not in user and "花子" not in user
    log = "".join(p.read_text(encoding="utf-8") for p in env["log"].glob("*.jsonl"))
    assert "花子" not in log
    c = con_of(env)
    assert "花子" in c.execute("SELECT transcript FROM drafts WHERE recording_id = ?", (rid,)).fetchone()[0]


# ---- 患者様を固定した録音 ----

def test_fixed_recording_goes_to_its_visit(env):
    reply = json.dumps({**{k: [] for k in memo.KEYS}, "done": [{"text": "根管充填", "quote": "根管充填をしました"}]})
    use(env, ScriptedMouth(reply))
    a = appt_of(env, "0123")
    rid = record(env, a)
    c = con_of(env)
    r = recpipe.get(c, rid)
    assert r["state"] == "転送待ち" and r["patient_id"] and r["visit_id"]  # OK か転送を待つ
    assert (Path(env["dir"]) / "audio" / f"rec_{rid}.webm").read_bytes() == b"RIFFfake-webm"  # 先に音声を保存
    assert c.execute("SELECT COUNT(*) FROM drafts WHERE recording_id = ?", (rid,)).fetchone()[0] == 0
    assert api(env, "post", f"/rec/{rid}/transfer", json={})[0] == 200
    r = wait_state(env, rid, ["下書き", "失敗"])
    assert r["state"] == "下書き"
    d = c.execute("SELECT * FROM drafts WHERE id = ?", (r["draft_id"],)).fetchone()
    v = c.execute("SELECT * FROM visits WHERE id = ?", (d["visit_id"],)).fetchone()
    assert d["patient_id"] == r["patient_id"] == v["patient_id"] and d["status"] == "draft" and d["recording_id"] == rid
    assert json.loads(d["items"])["done"][0]["text"] == "根管充填"


def test_patientless_recording_stops_after_transcription_until_assigned(env):
    mouth = use(env, ScriptedMouth(EMPTY))
    rid = record(env, None)
    r = wait_state(env, rid, ["転送待ち", "失敗"])
    assert r["state"] == "転送待ち" and r["patient_id"] is None and r["transcript"]
    time.sleep(0.3)
    assert mouth.sent == []  # 転送先が決まるまで Claude へ送らない
    assert api(env, "post", f"/rec/{rid}/transfer", json={})[0] == 400  # 患者様を選ばないと転送できない
    b = appt_of(env, "0456")
    assert api(env, "post", f"/rec/{rid}/transfer", json={"appt": b})[0] == 200
    r = wait_state(env, rid, ["下書き", "失敗"])
    assert r["state"] == "下書き" and len(mouth.sent) == 1
    c = con_of(env)
    d = c.execute("SELECT * FROM drafts WHERE id = ?", (r["draft_id"],)).fetchone()
    assert c.execute("SELECT chart_no FROM patients WHERE id = ?", (d["patient_id"],)).fetchone()[0] == "0456"
    assert c.execute("SELECT appointment_id FROM visits WHERE id = ?", (d["visit_id"],)).fetchone()[0] == b


def test_drafts_of_two_patients_do_not_mix(env):
    reply = lambda t, q: json.dumps({**{k: [] for k in memo.KEYS}, "done": [{"text": t, "quote": q}]})  # noqa: E731
    ids = {}
    for chart, talk in (("0123", "根管充填をしました"), ("0456", "歯石除去をしました")):
        use(env, ScriptedMouth(reply(talk[:4], talk[:4])), f"今日は{talk}。")
        ids[chart] = record(env, appt_of(env, chart))
        api(env, "post", f"/rec/{ids[chart]}/transfer", json={})
        wait_state(env, ids[chart], ["下書き"])
    c = con_of(env)
    rows = {r["chart_no"]: r for r in c.execute(
        "SELECT p.chart_no, d.* FROM drafts d JOIN patients p ON p.id = d.patient_id WHERE d.recording_id IS NOT NULL")}
    assert set(rows) == {"0123", "0456"}
    assert "根管充填" in rows["0123"]["transcript"] and "歯石" not in rows["0123"]["transcript"]
    assert "歯石" in rows["0456"]["transcript"] and "根管" not in rows["0456"]["transcript"]
    # 下書きの画面も、患者様ごとに別
    page = env["client"].get(f"/drafts/{rows['0123']['id']}").text
    assert "根管充填" in page and "歯石" not in page
    assert env["client"].get(f"/drafts/{rows['0123']['id']}?chart=0456").status_code == 404


def test_result_goes_to_fixed_patient_even_if_screen_moved_on(env):
    """遅れて届いた結果は、録音を始めたときの患者様の下書きにだけ入る（今開いている患者様は関係ない）。"""
    use(env, ScriptedMouth(EMPTY, delay_ms=800))
    rid = record(env, appt_of(env, "0123"))
    api(env, "post", f"/rec/{rid}/transfer", json={})
    other = record(env, appt_of(env, "0456"))  # 待っている間に別の患者様の録音も始まる
    r = wait_state(env, rid, ["下書き"])
    c = con_of(env)
    assert c.execute("SELECT chart_no FROM patients WHERE id = ?", (r["patient_id"],)).fetchone()[0] == "0123"
    assert c.execute("SELECT COUNT(*) FROM drafts WHERE patient_id = (SELECT id FROM patients WHERE chart_no='0456')"
                     " AND recording_id IS NOT NULL").fetchone()[0] == 0
    assert recpipe.get(c, other)["state"] == "転送待ち"


# ---- 失敗・再試行・二重 ----

def test_timeout_fails_then_retry_works_without_duplicates(env):
    env["mp"].setenv("CHAIRSIDE_AI_TIMEOUT", "0.4")
    slow = use(env, ScriptedMouth(EMPTY, delay_ms=1500))
    rid = record(env, appt_of(env, "0123"))
    api(env, "post", f"/rec/{rid}/transfer", json={})
    r = wait_state(env, rid, ["失敗"])
    assert "時間切れ" in r["error"]
    assert api(env, "post", f"/rec/{rid}/later")[0] == 200  # 後で直す
    assert recpipe.get(con_of(env), rid)["state"] == "後で直す"
    slow.delay_ms = 0
    env["mp"].setenv("CHAIRSIDE_AI_TIMEOUT", "30")
    codes = [api(env, "post", f"/rec/{rid}/retry")[0], api(env, "post", f"/rec/{rid}/retry")[0]]  # 二重に押す
    assert sorted(codes) == [200, 409]
    wait_state(env, rid, ["下書き"])
    time.sleep(1.8)  # 最初の遅い処理が終わっても、状態も下書きも変わらない
    c = con_of(env)
    assert recpipe.get(c, rid)["state"] == "下書き"
    assert c.execute("SELECT COUNT(*) FROM drafts WHERE recording_id = ?", (rid,)).fetchone()[0] == 1
    assert api(env, "post", f"/rec/{rid}/retry")[0] == 409  # 下書きになったものは再試行できない


def test_retry_from_saved_audio_after_server_restart(env):
    use(env, ScriptedMouth(EMPTY))
    rid = record(env, appt_of(env, "0123"))
    c = con_of(env)
    # 整理の途中でサーバーが止まった状態: 作業中のまま、動いている処理が無い
    c.execute("UPDATE recordings SET state = '整理中', attempt = 5, updated_at = '2020-01-01T00:00:00' WHERE id = ?", (rid,))
    c.commit()
    code, d = api(env, "get", "/api/recordings")
    row = next(x for x in d["recordings"] if x["id"] == rid)
    assert row["state"] == "失敗" and "中断" in row["error"]
    assert (Path(env["dir"]) / "audio" / f"rec_{rid}.webm").exists()  # 音声は残っている
    assert api(env, "post", f"/rec/{rid}/retry")[0] == 200
    wait_state(env, rid, ["下書き"])
    assert c.execute("SELECT COUNT(*) FROM drafts WHERE recording_id = ?", (rid,)).fetchone()[0] == 1


def test_claude_unavailable_and_bad_reply_fail_cleanly(env):
    use(env, ScriptedMouth("これは JSON ではありません"))
    rid = record(env, appt_of(env, "0123"))
    api(env, "post", f"/rec/{rid}/transfer", json={})
    r = wait_state(env, rid, ["失敗"])
    assert r["error"] and "sk-" not in r["error"]


def test_transcription_failure_is_a_failure(env):
    use(env, ScriptedMouth(EMPTY), transcript="")
    env["mp"].setattr(recpipe.fake, "fake_transcript", lambda: (_ for _ in ()).throw(RuntimeError("文字起こしの機械が動きません")))
    rid = record(env, appt_of(env, "0123"))
    api(env, "post", f"/rec/{rid}/transfer", json={})
    r = wait_state(env, rid, ["失敗"])
    assert "文字起こし" in r["error"]
    env["mp"].setattr(recpipe.fake, "fake_transcript", lambda: "今日は根管充填をしました。")
    assert api(env, "post", f"/rec/{rid}/retry")[0] == 200
    wait_state(env, rid, ["下書き"])


# ---- 文字を貼り付ける口 ----

def test_paste_runs_same_pipeline(env):
    reply = json.dumps({**{k: [] for k in memo.KEYS}, "done": [{"text": "SPT", "quote": "SPTをしました"}]})
    use(env, ScriptedMouth(reply))
    code, r = api(env, "post", "/rec/paste", json={"text": "今日はSPTをしました。", "appt": appt_of(env, "0123")})
    assert code == 200
    wait_state(env, r["id"], ["下書き"])
    code, r2 = api(env, "post", "/rec/paste", json={"text": "今日はSPTをしました。"})
    assert recpipe.get(con_of(env), r2["id"])["state"] == "転送待ち"  # 患者様なし
    assert api(env, "post", "/rec/paste", json={"text": "  "})[0] == 400


def test_recordings_list_has_columns(env):
    use(env, ScriptedMouth(EMPTY))
    rid = record(env, None)
    wait_state(env, rid, ["転送待ち"])
    code, d = api(env, "get", "/api/recordings")
    row = d["recordings"][0]
    assert set(row) >= {"time", "duration", "chart_no", "state"} and row["duration"] == "01:24"
    assert row["chart_no"] == "患者様なし" and d["pending"] == 1
    page = env["client"].get("/recordings").text
    for col in ("時間", "長さ", "カルテ番号", "状態"):
        assert col in page


def test_draft_page_has_mark_and_two_sides(env):
    reply = json.dumps({**{k: [] for k in memo.KEYS}, "next_plan": [{"text": "土台", "quote": "土台を立てます"}]})
    use(env, ScriptedMouth(reply))
    rid = record(env, appt_of(env, "0123"))
    api(env, "post", f"/rec/{rid}/transfer", json={})
    r = wait_state(env, rid, ["下書き"])
    page = env["client"].get(f"/drafts/{r['draft_id']}").text
    assert "下書き まだ記録に入っていません" in page
    for t in ("話したままの文字", "今日やったこと", "説明したこと", "次回の予定", "今後の治療計画", "今後の治療方針", "もとの話: 土台を立てます"):
        assert t in page
