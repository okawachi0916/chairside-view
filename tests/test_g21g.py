"""G21g: 治療歴と「前回」は診療日の順。過去の回を直しても並びと「前回」は変わらない。撮影前の戻す道具。"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.ai import ask as ask_mod
from app.ai.records import build_records
from app.db import TODAY, connect
from app.views import data as D

ROOT = Path(__file__).resolve().parents[1]


def seed(d, extra=None):
    env = {**os.environ, "CV_DATA_DIR": str(d), "PYTHONIOENCODING": "utf-8", **(extra or {})}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], env=env, capture_output=True)
    assert r.returncode == 0, r.stderr
    return env


@pytest.fixture
def db(tmp_path, monkeypatch):
    seed(tmp_path)
    monkeypatch.setenv("CV_DATA_DIR", str(tmp_path))
    c = connect()
    yield c
    c.close()


def prev(c, pid, visit_date):
    res = ask_mod.answer("前回は何をした？", c, pid, None, visit_date=visit_date)
    assert res["result"] == "found", res
    return res["ref"]


def test_previous_is_latest_before_visit_and_stable_after_editing_old_visit(db):
    pid = db.execute("SELECT id FROM patients WHERE chart_no='0123'").fetchone()[0]
    first = prev(db, pid, TODAY)
    assert first.startswith("note:") and first[5:] < TODAY
    # 古い日付の回を、あとから（いちばん新しい id で）足す・直す → 「前回」は変わらない
    db.execute("INSERT INTO clinical_notes (patient_id, visit_id, note_date, author_role, body) VALUES (?, (SELECT MIN(id) FROM visits), '2020-01-01', 'doctor', '古い回を直した')", (pid,))
    db.execute("UPDATE clinical_notes SET body = body || '（直した）' WHERE patient_id = ? AND note_date = ?", (pid, first[5:]))
    db.commit()
    assert prev(db, pid, TODAY) == first
    # 今開いている回の日付以降の記録は「前回」にならない
    db.execute("INSERT INTO clinical_notes (patient_id, visit_id, note_date, author_role, body) VALUES (?, (SELECT MIN(id) FROM visits), ?, 'doctor', '今日の回')", (pid, TODAY))
    db.commit()
    assert prev(db, pid, TODAY) == first
    assert prev(db, pid, "2030-01-01") == "note:" + TODAY
    # 開いている回がもっと前なら、その前の回
    older = prev(db, pid, first[5:])
    assert older[5:] < first[5:]


def test_history_list_is_by_date_not_insert_order(db):
    pid = db.execute("SELECT id FROM patients WHERE chart_no='0123'").fetchone()[0]
    appt = dict(db.execute("SELECT * FROM appointments WHERE patient_id=? LIMIT 1", (pid,)).fetchone())
    before = [r["done_date"] for r in D.unit_data(appt, "doctor")["history"]]
    assert before == sorted(before, reverse=True)
    db.execute("INSERT INTO treatment_history (patient_id, done_date, site, content) VALUES (?, '2019-01-01', '全顎', '古い回を後から入れた')", (pid,))
    db.execute("UPDATE treatment_history SET content = content || '（直した）' WHERE patient_id = ? AND done_date = ?", (pid, before[0]))
    db.commit()
    after = [r["done_date"] for r in D.unit_data(appt, "doctor")["history"]]
    assert after == before + ["2019-01-01"]
    ids = [r.ref for r in build_records(db, pid) if r.ref.startswith("history:") or r.ref.startswith("note:")]
    assert ids  # 記録の番号付けは日付順で決まる


def test_reset_script_backs_up_then_restores(tmp_path):
    data = tmp_path / "data"
    backups = tmp_path / "backups"
    env = seed(data, {"CV_DEMO_DIR": str(backups)})
    con = sqlite3.connect(data / "app.db")
    con.execute("INSERT INTO clinical_notes (patient_id, visit_id, note_date, author_role, body) VALUES (1, (SELECT MIN(id) FROM visits), '2026-11-04', 'doctor', '試しの記録')")
    con.commit(); con.close()
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "reset_for_shoot.py")], env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    saved = list((backups / "db_backups").glob("app_*.db"))
    assert len(saved) == 1
    old = sqlite3.connect(saved[0])
    assert old.execute("SELECT COUNT(*) FROM clinical_notes WHERE body='試しの記録'").fetchone()[0] == 1
    old.close()
    now = sqlite3.connect(data / "app.db")
    assert now.execute("SELECT COUNT(*) FROM clinical_notes WHERE body='試しの記録'").fetchone()[0] == 0
    now.close()


def test_bat_file_bytes_are_plain_and_crlf():
    """G21h: bat は英数字と記号だけ（日本語の行を入れない）、改行は CRLF、reset_for_shoot.py の名前が化けていない。"""
    b = (ROOT / "scripts" / "撮影の前に戻す.bat").read_bytes()
    BS = chr(92)
    want = "scripts" + BS + "reset_for_shoot.py"
    assert want.encode() in b
    assert b.isascii()
    assert b.count(b"\r\n") == b.count(b"\n") == b.count(b"\r") and b.endswith(b"\r\n")
    assert all(0x20 <= c < 0x7f or c in (0x0d, 0x0a) for c in b)
    lines = b.decode("ascii").split("\r\n")[:-1]
    assert lines[0] == "@echo off" and lines[-1] == "pause"
    script = [x for x in lines if "reset_for_shoot.py" in x]
    assert len(script) == 1 and script[0].endswith(want)
    assert (ROOT / "scripts" / "reset_for_shoot.py").exists()
