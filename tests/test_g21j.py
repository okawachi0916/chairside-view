"""G21j: 美咲様（2048）の重要事項は「ラテックスアレルギー」だけ。かゆみの話が出ない。ほかの4人は変わらない。"""
import json
import sqlite3

from app.ai import ask as ask_mod
from app.db import initial, update as upd
from tests.test_g21i import ROOT, run  # noqa: F401


def test_initial_important_notes():
    d = initial.build()
    pats = {p["id"]: p["chart_no"] for p in d["patients"]}
    got = {}
    for n in d["important_notes"]:
        got.setdefault(pats[n["patient_id"]], []).append((n["body"], n["period"], n["detail"]))
    assert got["2048"] == [("ラテックスアレルギー", "2018年", "")]
    assert len(got) == 5 and got["0123"][0][2] and got["0456"][0][2]  # ほかの人の詳しくは今までどおり
    assert "かゆ" not in repr(d)


def test_update_clears_old_detail_in_existing_db(tmp_path):
    p = tmp_path / "a.db"
    upd.update(str(p))
    con = sqlite3.connect(p)
    con.execute("UPDATE important_notes SET detail='手袋で手がかゆくなった' WHERE body='ラテックスアレルギー'")
    con.commit(); con.close()
    upd.update(str(p))
    con = sqlite3.connect(p)
    assert con.execute("SELECT detail FROM important_notes WHERE body='ラテックスアレルギー'").fetchone()[0] == ""


def test_screens_and_answer_have_no_empty_leftovers(tmp_path, monkeypatch):
    import os, subprocess, sys
    probe = r'''
import json, re
from fastapi.testclient import TestClient
from app.main import app
from app.db import connect
from app.ai import ask
c = TestClient(app); con = connect()
pid = con.execute("SELECT id FROM patients WHERE chart_no='2048'").fetchone()[0]
out = {}
for role in ("doctor", "hygienist"):
    a = con.execute("SELECT id FROM appointments WHERE patient_id=? AND status='booked' AND role=? ORDER BY appt_date LIMIT 1", (pid, role)).fetchone()
    if a:
        out[role] = c.get("/api/view/unit", params={"appt": a[0], "role": role}).json()["html"]
rec = c.get("/api/view/reception", params={"patient": pid}).json()["html"]
out["reception"] = rec
res = ask.answer("アレルギーは？", con, pid, None)
out["answer"] = res
print(json.dumps(out, ensure_ascii=False))
'''
    env = {**os.environ, "CV_DATA_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    assert subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], env=env, capture_output=True).returncode == 0
    p = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert p.returncode == 0, p.stderr[-600:]
    o = json.loads(p.stdout.strip().splitlines()[-1])
    assert "かゆ" not in json.dumps(o, ensure_ascii=False)
    doc = o["doctor"]
    assert "ラテックスアレルギー" in doc and "<template data-fs=\"important\"" in doc
    assert "ラテックスアレルギー" in "".join(o["answer"]["lines"]) and "2018年" in "".join(o["answer"]["lines"])
    assert all("" != x.strip() and x.strip() not in ("（）", "()", "詳しく:", "詳しく: ") for x in o["answer"]["lines"])
    assert "（）" not in doc and "詳しく: <" not in doc
