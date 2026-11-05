"""G21i: 見本の「今日」はパソコンの日付（CV_TODAY で止められる）。過去の記録は年月日で出し、「今日」と書かない。"""
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PROBE = r'''
import json, sqlite3, sys, re
from fastapi.testclient import TestClient
from app.today import today
from app.main import app
from app.ai import ask
from app.ai.recpipe import today_str
from app.db import connect
c = TestClient(app)
con = connect()
out = {"today": today(), "rec_today": today_str()}
q = lambda s, *a: con.execute(s, a).fetchall()
out["future_rows"] = {
    "clinical_notes": q("SELECT COUNT(*) FROM clinical_notes WHERE note_date > ?", today())[0][0],
    "treatment_history": q("SELECT COUNT(*) FROM treatment_history WHERE done_date > ?", today())[0][0],
    "visits_past": q("SELECT COUNT(*) FROM visits WHERE visit_date > ?", today())[0][0],
    "photos": q("SELECT COUNT(*) FROM photos WHERE taken_on > ?", today())[0][0],
    "perio": q("SELECT COUNT(*) FROM perio_exams WHERE exam_date > ?", today())[0][0],
}
out["today_appts"] = q("SELECT COUNT(*) FROM appointments WHERE appt_date = ? AND status = 'booked'", today())[0][0]
pid = q("SELECT id FROM patients WHERE chart_no='0123'")[0][0]
res = ask.answer("前回は何をした？", con, pid, None, visit_date=today())
out["prev"] = res.get("ref")
cur = q("SELECT id FROM appointments WHERE patient_id=? AND appt_date=? AND role='doctor'", pid, today())[0][0]
page = c.get("/api/view/unit", params={"appt": cur}).json()
out["today_page_text"] = re.sub(r"<[^>]+>", "", page["html"])
m = re.search(r'data-part="past-notes".*?</div></section>', page["html"], re.S) or re.search(r'data-part="past-notes".*', page["html"], re.S)
out["past_notes_text"] = re.sub(r"<[^>]+>", "", m.group(0)) if m else ""
out["list"] = re.sub(r"<[^>]+>", "", c.get("/").text)
out["reception"] = re.sub(r"<[^>]+>", "", c.get("/api/view/reception", params={"patient": pid}).json()["html"])
print(json.dumps(out, ensure_ascii=False))
'''


def run(today, tmp_path):
    env = {**os.environ, "CV_DATA_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    if today:
        env["CV_TODAY"] = today
    else:
        env.pop("CV_TODAY", None)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], env=env, capture_output=True)
    assert r.returncode == 0, r.stderr
    p = subprocess.run([sys.executable, "-c", PROBE], env=env, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert p.returncode == 0, p.stderr[-800:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def ja(s):
    d = date.fromisoformat(s)
    return f"{d.year}年{d.month}月{d.day}日 {'月火水木金土日'[d.weekday()]}曜日"


@pytest.mark.parametrize("today", ["2026-11-04", "2027-01-15"])
def test_sample_today_follows_the_given_date(today, tmp_path):
    o = run(today, tmp_path)
    assert o["today"] == today == o["rec_today"]  # 録音の日付と画面の今日が同じ
    assert all(v == 0 for v in o["future_rows"].values()), o["future_rows"]
    assert o["today_appts"] >= 4
    assert ja(today) in o["list"] and ja(today) in o["today_page_text"]
    assert "2026年11月6日" not in o["list"] + o["today_page_text"] + o["reception"] or today == "2026-11-06"
    assert o["past_notes_text"] and "今日" not in o["past_notes_text"]  # 過去の診療メモに「今日」が無い（年月日で出る）
    # 「前回」は、日付をずらしても、今日の14日前（見本では 10/23）の診療メモ
    want = (date.fromisoformat(today) - timedelta(days=14)).isoformat()
    assert o["prev"] == "note:" + want
    assert "次回のご予約" in o["reception"]


def test_default_is_pc_date(tmp_path):
    o = run(None, tmp_path)
    assert o["today"] == date.today().isoformat() == o["rec_today"]


def test_fixed_date_still_matches_old_sample(tmp_path):
    o = run("2026-11-06", tmp_path)
    assert o["prev"] == "note:2026-10-23" and ja("2026-11-06") in o["list"]
