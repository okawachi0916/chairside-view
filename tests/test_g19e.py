"""G19e: 要約は年月日で書く / アレルギー・薬の記録が空でも答える / 聞き違いの言葉を足す。本物の Claude は呼ばない。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.ai import ask as ask_mod
from app.ai import fixtalk, memo
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from app.ai.redact import Sensitive

ROOT = Path(__file__).resolve().parents[1]
SENS = Sensitive(patients=[], staff=[], clinics=[])
FOUR = ["前回は何をした？", "アレルギーは？", "薬は？", "次回は？"]
ALLERGY_EMPTY = "アレルギーの記録がありません。アレルギーの無い方は「なし」または「特になし」と書いておきましょう。"
MEDICINE_EMPTY = "飲んでいる薬の記録がありません。飲んでいない方は「なし」または「特になし」と書いておきましょう。"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    d = tmp_path_factory.mktemp("g19e")
    env = {**os.environ, "CV_DATA_DIR": str(d), "PYTHONIOENCODING": "utf-8"}
    assert subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], env=env, capture_output=True).returncode == 0
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


class Boom(ScriptedMouth):
    """Claude へ送ったら数える口。表で答えられる質問は、1回も送らない。"""

    def __init__(self):
        super().__init__("{}")
        self.sent = 0

    def send(self, *a, **k):
        self.sent += 1
        return super().send(*a, **k)


def ask(db, pid, text):
    mouth = Boom()
    res = ask_mod.answer(text, db, pid, Gateway(mouth=mouth))
    return res, mouth


def patient_ids(db):
    return [r["id"] for r in db.execute("SELECT id FROM patients ORDER BY id")]


# ---- 1. 年月日 ----

def test_heading_has_the_visit_date_not_today():
    items = {k: [] for k in memo.KEYS}
    items["done"] = [{"text": "右下6番の根管充填。", "quote": "x"}]
    items["next_plan"] = [{"text": "2週間後に支台築造。", "quote": "x"}]
    body = memo.body_lines(items, "2026-11-06")
    assert body.splitlines()[0] == "2026年11月6日にやったこと: 右下6番の根管充填。"
    assert "次回の予定: 2週間後に支台築造。" in body and "今日" not in body
    assert memo.title_of("done", "2026-01-05") == "2026年1月5日にやったこと"
    assert memo.title_of("done") == "やったこと"  # 日付が分からないときも「今日」とは書かない


def test_prompt_does_not_ask_for_today():
    assert "今日やったこと" not in memo.SYSTEM and "今日やったこと" not in str(memo.SECTIONS)
    assert "「今日」" in memo.SYSTEM  # 「今日」と書かない決まりとして出てくる


def test_last_visit_answer_shows_the_date(db):
    pid = patient_ids(db)[3]
    vid = db.execute("SELECT id FROM visits WHERE patient_id = ? LIMIT 1", (pid,)).fetchone()["id"]
    items = {k_: [] for k_ in memo.KEYS}
    items["done"] = [{"text": "左上6番のレジン充填。", "quote": "x"}]
    db.execute("INSERT INTO clinical_notes (patient_id, visit_id, note_date, author_role, body) VALUES (?, ?, ?, 'doctor', ?)",
               (pid, vid, "2026-11-06", memo.body_lines(items, "2026-11-06")))
    try:
        res, mouth = ask(db, pid, "前回は何をした？")
    finally:
        db.rollback()
    text = "".join(res["lines"])
    assert res["result"] == "found" and mouth.sent == 0
    assert "2026年11月6日にやったこと" in text and "今日" not in text
    assert "2026年11月6日" in res["source"]


def test_confirmed_note_uses_the_visit_date(db):
    """確定すると診療メモの見出しは、その診療回の日付になる（draft の body も同じ）。"""
    from app.ai import confirm

    pid = patient_ids(db)[0]
    vid = db.execute("SELECT id FROM visits WHERE patient_id = ? AND visit_date = '2026-11-06' LIMIT 1", (pid,)).fetchone()
    assert vid, "見本に今日の診療回がある"
    items = {k: [] for k in memo.KEYS}
    items["done"] = [{"text": "右下6番の根管充填。", "quote": "根管充填"}]
    d = db.execute("INSERT INTO drafts (patient_id, visit_id, kind, body, transcript, status, created_at, items) "
                   "VALUES (?, ?, 'spoken_summary', '', '根管充填', 'draft', '2026-11-06 14:50', ?)",
                   (pid, vid["id"], json.dumps(items, ensure_ascii=False))).lastrowid
    db.commit()
    try:
        confirm.save_items(db, d, items)
        assert db.execute("SELECT body FROM drafts WHERE id = ?", (d,)).fetchone()["body"].startswith("2026年11月6日にやったこと: ")
        confirm.confirm(db, d, items)
        note = db.execute("SELECT body FROM clinical_notes WHERE visit_id = ? ORDER BY id DESC", (vid["id"],)).fetchone()["body"]
        assert note.startswith("2026年11月6日にやったこと: ") and "今日" not in note
    finally:
        db.execute("DELETE FROM clinical_notes WHERE visit_id = ? AND body LIKE '2026年11月6日にやったこと%'", (vid["id"],))
        db.execute("DELETE FROM drafts WHERE id = ?", (d,))
        db.commit()


# ---- 2. アレルギー・薬が空でも答える ----

def test_allergy_nothing_is_shown_as_written(db):
    t = patient_ids(db)[2]
    res, mouth = ask(db, t, "アレルギーは？")
    assert res["result"] == "found" and mouth.sent == 0
    assert "アレルギー: 特になし" in res["lines"]


def test_empty_allergy_tells_how_to_write_it(db):
    k = patient_ids(db)[3]
    res, mouth = ask(db, k, "アレルギーは？")
    assert res["result"] == "none" and res["message"] == ALLERGY_EMPTY and mouth.sent == 0


def test_empty_medicine_tells_how_to_write_it(db):
    k = patient_ids(db)[3]
    db.execute("DELETE FROM medical_histories WHERE patient_id = ?", (k,))
    try:
        res, mouth = ask(db, k, "薬は？")
    finally:
        db.rollback()
    assert res["result"] == "none" and res["message"] == MEDICINE_EMPTY and mouth.sent == 0


def test_medicine_nothing_is_shown_as_written(db):
    k = patient_ids(db)[3]
    db.execute("DELETE FROM medical_histories WHERE patient_id = ?", (k,))
    db.execute("INSERT INTO medical_histories (patient_id, seq, condition, medication, since, clinic) VALUES (?, 1, '特になし', '', '', '')", (k,))
    try:
        res, _ = ask(db, k, "薬は？")
    finally:
        db.rollback()
    assert res["result"] == "found" and "特になし" in "".join(res["lines"])


def test_patient_with_no_records_at_all_still_gets_a_message(db):
    for q, want in (("アレルギーは？", ALLERGY_EMPTY), ("薬は？", MEDICINE_EMPTY)):
        res, mouth = ask(db, 99999, q)
        assert res["message"] == want and mouth.sent == 0
    for q in ("前回は何をした？", "次回は？"):
        res, mouth = ask(db, 99999, q)
        assert res["message"] and mouth.sent == 0


def test_sample_has_one_nothing_and_one_empty_allergy(db):
    ids = patient_ids(db)
    texts = {}
    for pid in ids:
        rows = [r["body"] for r in db.execute("SELECT body FROM important_notes WHERE patient_id = ?", (pid,))]
        rows += [r["condition"] for r in db.execute("SELECT condition FROM medical_histories WHERE patient_id = ?", (pid,))]
        texts[pid] = "".join(rows)
    assert sum("アレルギー: 特になし" in t for t in texts.values()) == 1
    assert sum("アレルギー" not in t for t in texts.values()) >= 1


@pytest.mark.parametrize("q", FOUR)
def test_four_voice_questions_always_give_something(db, q):
    for pid in patient_ids(db):
        res, mouth = ask(db, pid, q)
        assert mouth.sent == 0, (pid, q)  # 表で答える（Claude へ送らない）
        assert res["result"] == "found" and res["lines"] or res["message"], (pid, q, res)


def test_four_questions_in_the_empty_case_never_send_to_claude(db):
    for q in FOUR:
        res, mouth = ask(db, 99999, q)
        assert res["message"] and mouth.sent == 0


# ---- 3. 聞き違いの言葉 ----

def test_new_terms_and_rules_in_config():
    cfg = json.loads((ROOT / "config" / "dental_terms.json").read_text(encoding="utf-8"))
    for w in ("全身既往", "既往歴", "根尖病変", "服薬"):
        assert w in cfg["terms"]
    assert len(cfg["terms"]) <= 80
    assert "全身起用" in cfg["readings"]["全身既往"] and "今前病変" in cfg["readings"]["根尖病変"]
    assert "陰霊" in cfg["readings"]["インレー"]


def test_doctors_recording_sentences_are_fixed():
    mouth = ScriptedMouth("{}", fix_reply="[]")
    gw = Gateway(mouth=mouth, log_dir=Path(os.environ.get("TEMP", ".")) / "g19e_log")
    talk = "全身起用で貧血があります。今前病変はありましたが、左上6番に陰霊を入れました。"
    text, done = fixtalk.fix_transcript(talk, SENS, gw)
    assert text == "全身既往で貧血があります。根尖病変はありましたが、左上6番にインレーを入れました。"
    assert {(d["from"], d["to"]) for d in done} == {("全身起用", "全身既往"), ("今前病変", "根尖病変"), ("陰霊", "インレー")}
    assert all(d["by"] == "rule" for d in done)
    # 正しい言葉はそのまま
    ok = "全身既往と根尖病変とインレーです。"
    assert fixtalk.fix_transcript(ok, SENS, gw)[0] == ok
