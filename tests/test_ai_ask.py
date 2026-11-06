"""G16: 自由な質問に答える機能の試験。本物の Claude は呼ばない（偽物の口）。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import ask as ask_mod
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from app.ai.records import build_records
from app.ai.settings import ClaudeUnavailable

ROOT = Path(__file__).resolve().parents[1]
Q = json.loads((ROOT / "tests" / "questions.json").read_text(encoding="utf-8"))
CASES = Q["cases"]
ASKED = [c for c in CASES if c["kind"] == "質問"]
Q_CLAUDE = "ペニシリンの記録は？"  # 表（config/quick_answers.json）に当たらないので、必ず Claude に聞く質問


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    d = tmp_path_factory.mktemp("g16")
    env = {**os.environ, "CV_DATA_DIR": str(d), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], env=env, capture_output=True)
    assert r.returncode == 0
    old = os.environ.get("CV_DATA_DIR")
    os.environ["CV_DATA_DIR"] = str(d)
    from app.db import connect

    con = connect(d / "app.db")
    yield con
    con.close()
    if old is None:
        os.environ.pop("CV_DATA_DIR", None)
    else:
        os.environ["CV_DATA_DIR"] = old


@pytest.fixture(scope="module")
def hanako(db):
    row = db.execute("SELECT id FROM patients WHERE chart_no = ?", (Q["patient"]["chart_no"],)).fetchone()
    assert db.execute("SELECT name FROM patients WHERE id = ?", (row["id"],)).fetchone()["name"].replace("　", " ") \
        == Q["patient"]["name"]
    return row["id"]


@pytest.fixture(scope="module")
def appt(db, hanako):
    return db.execute("SELECT id FROM appointments WHERE patient_id = ? AND appt_date = ? LIMIT 1", (hanako, "2026-11-06")).fetchone()["id"]


@pytest.fixture
def client(db):
    from app.main import app

    return TestClient(app)


def use_mouth(monkeypatch, tmp_path, mouth):
    import app.routers.ai as router

    monkeypatch.setattr(router, "make_gateway", lambda: Gateway(mouth=mouth, log_dir=tmp_path / "log"))
    return mouth


def post(client, appt, text):
    r = client.post("/ai/ask", json={"text": text, "appt": appt})
    assert r.status_code == 200
    return r.json()


def has(word, text):
    """英字の言葉は前に英字が続かないものだけ数える（RCT の中の CT は CT 撮影ではない）。"""
    import re

    return bool(re.search((r"(?<![A-Za-z])" if word.isascii() else "") + re.escape(word), text))


def number_of(records, ref):
    return next(r.number for r in records if r.ref == ref)


# ---- 本物の Claude へ送る前に、記録そのものを確かめる ----

@pytest.mark.parametrize("case", [c for c in ASKED if c["expect"]["result"] == "found"], ids=lambda c: f"case{c['id']}")
def test_correct_record_exists(db, hanako, case):
    records = build_records(db, hanako)
    rec = next((r for r in records if r.ref == case["expect"]["ref"]), None)
    assert rec is not None, case["expect"]["ref"]
    assert rec.source == case["expect"]["source"]
    if "contains" in case["expect"]:
        assert case["expect"]["contains"] in "".join(rec.lines)


@pytest.mark.parametrize("case", [c for c in ASKED if c["expect"]["result"] == "none"], ids=lambda c: f"case{c['id']}")
def test_none_questions_have_no_record(db, hanako, case):
    whole = "\n".join(r.prompt + "\n".join(r.lines) for r in build_records(db, hanako))
    for word in case["absent"]:
        assert not has(word, whole), word
    # 画面に出る別の表（歯の状態・義歯・粘膜など）にも無いこと
    for table, col in [("tooth_status", "status"), ("dentures", "kind"), ("mucosal_conditions", "name"),
                       ("prescriptions", "drug"), ("care_purchases", "item")]:
        for r in db.execute(f"SELECT {col} FROM {table} WHERE patient_id = ?", (hanako,)):
            for word in case["absent"]:
                assert not has(word, r[0] or ""), (table, word)


def test_record_numbers_are_unique_and_from_one(db, hanako):
    records = build_records(db, hanako)
    assert [r.number for r in records] == list(range(hanako * 100 + 1, hanako * 100 + len(records) + 1))
    assert len({r.ref for r in records}) == len(records)


# ---- 10例 ----

@pytest.mark.parametrize("case", CASES, ids=lambda c: f"case{c['id']}")
def test_ten_cases(client, db, hanako, appt, monkeypatch, tmp_path, case):
    records = build_records(db, hanako)
    exp = case["expect"]
    if exp["result"] == "found":
        reply = json.dumps({"result": "found", "record": number_of(records, exp["ref"])})
    elif exp["result"] == "none":
        reply = '{"result":"none"}'
    else:
        reply = '{"result":"found","record":101}'  # 送られないはずなので、何を返してもよい
    mouth = use_mouth(monkeypatch, tmp_path, ScriptedMouth(reply))
    res = post(client, appt, case["text"])
    assert len(mouth.sent) == case["sends"] and res["sends"] == case["sends"]
    assert res["result"] == exp["result"]
    if exp["result"] == "found":
        rec = next(r for r in records if r.ref == exp["ref"])
        assert res["ref"] == exp["ref"] and res["source"] == exp["source"]
        assert res["lines"] == rec.lines  # データベースの本文そのまま
    else:
        assert res["message"] == exp["message"]
        assert "lines" not in res


@pytest.mark.parametrize("case", ASKED, ids=lambda c: f"case{c['id']}")
def test_claude_path_without_table(db, hanako, tmp_path, case):
    """表を使わず Claude に聞く道筋でも、10例は同じ答えになる（Claude が正しく選んだ場合）。"""
    records = build_records(db, hanako)
    exp = case["expect"]
    reply = (json.dumps({"result": "found", "record": number_of(records, exp["ref"])}) if exp["result"] == "found"
             else '{"result":"none"}')
    mouth = ScriptedMouth(reply)
    res = ask_mod.answer(case["text"], db, hanako, Gateway(mouth=mouth, log_dir=tmp_path / "log"), quick=False)
    assert len(mouth.sent) == case.get("claude_sends", case["sends"]) == res["sends"]
    assert res["result"] == exp["result"] and res.get("ref") == exp.get("ref")


# ---- よく聞く質問は Claude を通さず記録から直接出す（config/quick_answers.json） ----

QUICK = [("前回は何をした？", "note:2026-10-23"), ("前回は？", "note:2026-10-23"), ("この前は何をしましたか", "note:2026-10-23"),
         ("アレルギーは？", "important:1"), ("アレルギーはありますか", "important:1"), ("アレルギーを教えて", "important:1"),
         ("飲んでいる薬は？", "medical"), ("お薬は？", "medical"), ("薬は何を飲んでいますか", "medical"),
         ("次回は何をする予定？", "next:1"), ("次は何をする予定？", "next:1"), ("次回は？", "next:1"), ("今後の予定は？", "next:1")]


@pytest.mark.parametrize("text,ref", QUICK)
def test_common_questions_skip_claude(client, db, hanako, appt, monkeypatch, tmp_path, text, ref):
    mouth = use_mouth(monkeypatch, tmp_path, ScriptedMouth("これは使われない"))
    res = post(client, appt, text)
    assert mouth.sent == [] and res["sends"] == 0
    rec = next(r for r in build_records(db, hanako) if r.ref == ref)
    assert res["result"] == "found" and res["ref"] == ref and res["lines"] == rec.lines  # データベースの本文そのまま
    assert not list((tmp_path / "log").glob("*.jsonl"))  # 送った記録も無い


# 言葉が混ざる質問・2項目にまたがる質問は、表で当てずに Claude へ回す
NOT_QUICK = ["前回の右下6番の治療はいつ？", "次回の予約はいつ？", "前回の薬は？", "アレルギーと薬は？", "昨日のアレルギーの検査は？",
             "前回の歯周検査の結果は？", "薬を飲み始めたのはいつ？", "右下6番の次回の予定は？", "アレルギーが出たのはいつ？"]


@pytest.mark.parametrize("text", NOT_QUICK)
def test_mixed_questions_go_to_claude(client, appt, monkeypatch, tmp_path, text):
    from app.ai.quick import pick_entry

    assert pick_entry(text) is None
    mouth = use_mouth(monkeypatch, tmp_path, ScriptedMouth('{"result":"none"}'))
    res = post(client, appt, text)
    assert len(mouth.sent) == 1 and res["sends"] == 1


def test_quick_miss_gives_the_empty_message_when_no_record(db, tmp_path):
    """G19e: アレルギーの記録が無く、ほかの記録にもその言葉が無い患者様は、Claude に聞かず「記録がありません」を出す。"""
    pid = next(r["id"] for r in db.execute("SELECT id FROM patients WHERE chart_no = '1024'"))
    assert not any("アレルギー" in "".join(r.lines) for r in build_records(db, pid) if r.part == "important")
    mouth = ScriptedMouth('{"result":"none"}')
    res = ask_mod.answer("アレルギーは？", db, pid, Gateway(mouth=mouth, log_dir=tmp_path / "log"))
    assert res["result"] == "none" and "アレルギーの記録がありません" in res["message"] and not mouth.sent


def test_quick_miss_goes_to_claude_when_another_record_mentions_it(db, tmp_path):
    """重要事項に無くても、ほかの記録にアレルギーの言葉があるなら、記録が無いと決めつけず Claude に回す。"""
    pid = next(r["id"] for r in db.execute("SELECT id FROM patients WHERE chart_no = '1024'"))
    vid = db.execute("SELECT id FROM visits WHERE patient_id = ? LIMIT 1", (pid,)).fetchone()["id"]
    db.execute("INSERT INTO clinical_notes (patient_id, visit_id, note_date, author_role, body) VALUES (?, ?, '2026-11-05', 'doctor', ?)",
               (pid, vid, "麻酔のあとアレルギーの症状なし"))
    try:
        mouth = ScriptedMouth('{"result":"none"}')
        res = ask_mod.answer("アレルギーは？", db, pid, Gateway(mouth=mouth, log_dir=tmp_path / "log"))
    finally:
        db.rollback()
    assert len(mouth.sent) == 1 and res["sends"] == 1


def test_quick_table_is_in_config_and_broken_file_falls_back(monkeypatch, tmp_path):
    from app.ai import quick

    t = quick.load_table()
    assert {e["name"] for e in t["entries"]} == {"前回", "アレルギー", "薬", "次回"}
    bad = tmp_path / "q.json"
    bad.write_text("{壊れている", encoding="utf-8")
    monkeypatch.setattr(quick, "CONFIG", bad)
    assert quick.pick_entry("アレルギーは？") is None  # 表が読めないときは全部 Claude へ
    monkeypatch.setattr(quick, "CONFIG", tmp_path / "none.json")
    assert quick.pick_entry("アレルギーは？") is None


def test_questions_json_matches_interpreter():
    from app.voice.interpret import interpret

    for c in CASES:
        assert interpret(c["text"], "unit")["kind"] == c["kind"], c["id"]


# ---- 3つの答え方 ----

def test_three_answers_all_shown(client, db, hanako, appt, monkeypatch, tmp_path):
    records = build_records(db, hanako)
    mouth = use_mouth(monkeypatch, tmp_path, ScriptedMouth())
    mouth.reply = json.dumps({"result": "found", "record": records[0].number})
    assert post(client, appt, Q_CLAUDE)["result"] == "found"
    mouth.reply = '{"result":"none"}'
    assert post(client, appt, Q_CLAUDE)["message"] == "記録がありません"
    mouth.reply = '{"result":"unclear"}'
    assert post(client, appt, Q_CLAUDE)["message"] == "もう一度お願いします"


BAD = [
    "{\"result\":\"found\",\"record\":9999}",              # 渡していない番号
    "{\"result\":\"found\",\"record\":0}",
    "{\"result\":\"found\",\"record\":1}",           # 番号の範囲の外
    "{\"result\":\"found\",\"record\":-1}",
    "{\"result\":\"found\",\"record\":\"101\"}",             # 数字ではなく文字
    "{\"result\":\"found\",\"record\":true}",
    "{\"result\":\"found\",\"record\":101.0}",
    "{\"result\":\"found\"}",
    "{\"result\":\"found\",\"record\":101,\"comment\":\"抜歯をおすすめします\"}",
    "{\"result\":\"none\",\"reason\":\"診断: 歯周病の疑い\"}",
    "{\"result\":\"maybe\"}",
    "[1]",
    "1",
    "null",
    "右下6番の根管治療です",
    "",
]


@pytest.mark.parametrize("reply", BAD)
def test_bad_replies_never_reach_screen(client, appt, monkeypatch, tmp_path, reply):
    use_mouth(monkeypatch, tmp_path, ScriptedMouth(reply))
    res = post(client, appt, Q_CLAUDE)
    assert res["result"] == "retry" and res["message"] == "もう一度お願いします"
    assert "lines" not in res and "ref" not in res
    assert "抜歯" not in json.dumps(res, ensure_ascii=False) and "診断" not in json.dumps(res, ensure_ascii=False)


def test_other_patients_number_is_rejected(client, db, hanako, appt, monkeypatch, tmp_path):
    other = next(r["id"] for r in db.execute("SELECT id FROM patients WHERE id != ?", (hanako,)))
    n = build_records(db, other)[0].number  # 別の患者様の1番目の記録の番号
    assert n not in {r.number for r in build_records(db, hanako)}
    use_mouth(monkeypatch, tmp_path, ScriptedMouth(json.dumps({"result": "found", "record": n})))
    res = post(client, appt, Q_CLAUDE)
    assert res["result"] == "retry" and "lines" not in res


def test_fenced_json_is_accepted():
    assert ask_mod.parse_reply('```json\n{"result":"none"}\n```', {1}) == ("none",)


def test_claude_text_is_never_shown(client, db, hanako, appt, monkeypatch, tmp_path):
    records = build_records(db, hanako)
    use_mouth(monkeypatch, tmp_path, ScriptedMouth(json.dumps({"result": "found", "record": records[0].number})))
    res = post(client, appt, Q_CLAUDE)
    assert set(res) == {"result", "title", "lines", "source", "part", "ref", "sends"}
    assert res["lines"] == records[0].lines


# ---- 送らない場合 ----

UNRELATED = ["大きく口を開けてください", "右下6番を見てください", "今日はいい天気ですね", "ありがとうございました",
             "お口を閉じてください", "少し痛みますよ", "麻酔をしますね", "うがいをしてください",
             "次の方をお呼びします", "もう少しで終わります"]


def test_unrelated_words_send_nothing(client, appt, monkeypatch, tmp_path):
    from app.voice.interpret import QUESTION, interpret

    mouth = use_mouth(monkeypatch, tmp_path, ScriptedMouth('{"result":"none"}'))
    assert len(UNRELATED) == 10
    for w in UNRELATED:
        assert interpret(w, "unit")["kind"] != QUESTION, w  # 質問に分けられない言葉を選んである
        res = post(client, appt, w)
        assert res["result"] == "skip" and res["sends"] == 0, w
    assert mouth.sent == []


def test_operations_and_failures_send_nothing(client, appt, monkeypatch, tmp_path):
    mouth = use_mouth(monkeypatch, tmp_path, ScriptedMouth('{"result":"none"}'))
    for w in ["重要事項を全画面にして", "戻して", "", "あの", "えっと", "あのあのあの"]:
        assert post(client, appt, w)["sends"] == 0
    assert mouth.sent == []


# ---- 送る中身と失敗 ----

def test_sent_text_has_records_but_no_names(client, db, hanako, appt, monkeypatch, tmp_path):
    mouth = use_mouth(monkeypatch, tmp_path, ScriptedMouth('{"result":"none"}'))
    post(client, appt, "見本 花子様のアレルギーは？")
    system, user = mouth.sent[0]
    assert "見本" not in user and "花子" not in user
    assert "記録101:" in user and "質問:" in user
    assert "診断も治療の提案もしません" in system
    log = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "log").glob("*.jsonl"))
    assert "花子" not in log


def test_unavailable_when_no_key(client, appt, monkeypatch, tmp_path):
    class NoKey:
        def complete(self, *a):
            raise ClaudeUnavailable("鍵が無い")

    use_mouth(monkeypatch, tmp_path, NoKey())
    res = post(client, appt, Q_CLAUDE)
    assert res["result"] == "unavailable" and "使えません" in res["message"]


def test_network_error_shows_retry_without_details(client, appt, monkeypatch, tmp_path):
    class Boom:
        def complete(self, *a):
            raise ConnectionError("sk-test-secret-1 接続できません")

    monkeypatch.setenv("CHAIRSIDE_CLAUDE_KEY", "sk-test-secret-1")
    use_mouth(monkeypatch, tmp_path, Boom())
    res = post(client, appt, Q_CLAUDE)
    assert res["result"] == "retry" and "sk-test" not in json.dumps(res, ensure_ascii=False)


def test_unknown_appointment_is_404(client):
    assert client.post("/ai/ask", json={"text": Q_CLAUDE, "appt": 999999}).status_code == 404
