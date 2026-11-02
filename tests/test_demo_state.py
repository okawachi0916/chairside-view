"""G20: 動画の撮影用 scripts/demo_state.py。一時フォルダで 写す → 変える → 戻す を試す。"""
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import memo

ROOT = Path(__file__).resolve().parent.parent
TALK = "今日は右下6番の根管充填をしました。今後の治療計画は、右下6番は被せ物を入れます。"
GOOD = json.dumps({**{k: [] for k in memo.KEYS},
                   "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"}]}, ensure_ascii=False)
AUDIO = b"fake-webm-bytes-for-demo"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    rt, demo = tmp_path / "runtime", tmp_path / "demo"
    monkeypatch.setenv("CV_DATA_DIR", str(rt))
    monkeypatch.setenv("CV_DEMO_DIR", str(demo))
    fake = Path(os.environ["CHAIRSIDE_AI_FAKE_FILE"])
    old = fake.read_text(encoding="utf-8")
    fake.write_text(json.dumps({"reply": GOOD, "transcript": TALK}), encoding="utf-8")
    yield rt, demo
    fake.write_text(old, encoding="utf-8")


def run(*args, expect=0):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "demo_state.py"), *args], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == expect, r.stdout + r.stderr
    return r


def make_later(c):
    """録音 → 下書き → 後で直す。追記必要の印が付く。"""
    rows = c.get("/api/today").json()["rows"]
    appt = next(r["id"] for r in rows if r["chart_no"] == "0123" and r["role"] == "doctor")
    rid = c.post("/rec/start", json={"appt": appt}).json()["id"]
    c.post(f"/rec/{rid}/audio?dur=12", content=AUDIO)
    c.post(f"/rec/{rid}/transfer", json={})
    for _ in range(100):
        s = c.get(f"/api/recordings/{rid}").json()
        if s["state"] in ("下書き", "失敗"):
            break
        time.sleep(0.1)
    assert s["state"] == "下書き", s
    assert c.post(f"/rec/{rid}/later").status_code == 200
    return rid, appt


def marks(c):
    return [r["id"] for r in c.get("/api/today").json()["rows"] if r["mark"]]


def count(rt, sql):
    con = sqlite3.connect(rt / "app.db")
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def test_save_change_restore(env):
    rt, demo = env
    from app.db.update import update
    from app.main import app
    update()
    with TestClient(app) as c:
        rid, appt = make_later(c)
        assert marks(c) == [appt]
        audio = rt / "audio" / f"rec_{rid}.webm"
        assert audio.read_bytes() == AUDIO
        (rt / "drafts").mkdir(exist_ok=True)
        (rt / "drafts" / "memo.txt").write_text("元の下書き", encoding="utf-8")
        drafts_before = count(rt, "SELECT COUNT(*) FROM drafts")
        recs_before = count(rt, "SELECT COUNT(*) FROM recordings")

        run("save", "t1")
        assert (demo / "t1" / "app.db").exists() and (demo / "t1" / "audio" / audio.name).exists()

        # 変える: 音声を消し、印を消し、下書きを書き換え、新しい物を足す
        audio.unlink()
        (rt / "audio" / "extra.webm").write_bytes(b"x")
        (rt / "drafts" / "memo.txt").write_text("変えた", encoding="utf-8")
        (rt / "drafts" / "new.txt").write_text("新しい", encoding="utf-8")
        con = sqlite3.connect(rt / "app.db")
        con.execute("DELETE FROM recordings")
        con.execute("DELETE FROM drafts")
        con.execute("DELETE FROM patients WHERE id = 5")
        con.commit()
        con.close()
        assert marks(c) == []

        # サーバーが動いたまま (TestClient が開いたまま) 戻す
        run("restore", "t1")
        assert audio.read_bytes() == AUDIO and not (rt / "audio" / "extra.webm").exists()
        assert (rt / "drafts" / "memo.txt").read_text(encoding="utf-8") == "元の下書き"
        assert not (rt / "drafts" / "new.txt").exists()
        assert count(rt, "SELECT COUNT(*) FROM drafts") == drafts_before
        assert count(rt, "SELECT COUNT(*) FROM recordings") == recs_before
        assert count(rt, "SELECT COUNT(*) FROM patients") == 5  # 消した患者様も戻る
        assert marks(c) == [appt]
        assert c.get(f"/api/recordings/{rid}").json()["state"] == "後で直す"


def test_restore_runs_update_db(env):
    """古い形の写しを戻しても、そのあと update_db.py が足りない列と初期の行を足す。"""
    rt, demo = env
    from app.db.update import update
    update()
    run("save", "old")
    con = sqlite3.connect(demo / "old" / "app.db")
    con.execute("DELETE FROM photos")
    con.commit()
    con.close()
    run("restore", "old")
    assert count(rt, "SELECT COUNT(*) FROM photos") > 0


def test_bad_names_and_missing_state(env):
    run("restore", "ない名前", expect=1)
    run("save", "../escape", expect=1)
    run("save", "", expect=1)
    run("oops", "x", expect=2)
