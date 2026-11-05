"""G21k-4/5: 失敗を黙って飲み込まない。失敗したことと理由が記録（error_log.txt）に残る。"""
import json
import sqlite3

import pytest

from app import errlog
from app.ai import memo, recpipe
from app.views import photos as PH


@pytest.fixture
def logdir(tmp_path, monkeypatch):
    monkeypatch.setattr(errlog, "data_dir", lambda: tmp_path)
    return tmp_path


def log_text(d):
    p = d / "error_log.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_broken_photo_list_is_recorded_once_and_missing_list_is_told_apart(logdir, tmp_path, monkeypatch):
    PH._reported.clear()
    d = tmp_path / "ph"
    d.mkdir()
    monkeypatch.setenv("CV_PHOTO_DIR", str(d))
    assert PH.listing() == [] and "ありません" in log_text(logdir)  # 無い
    (d / "photos.json").write_text("{こわれている", encoding="utf-8")
    assert PH.listing() == [] and PH.cards() == []
    t = log_text(logdir)
    assert "読めません" in t and t.count("読めません") == 1  # 壊れている → 理由つきで1回だけ
    (d / "photos.json").write_text(json.dumps({"photos": [{"file": "a.jpg"}], "cards": []}), encoding="utf-8")
    assert PH.listing() == [{"file": "a.jpg"}]


def test_audio_that_cannot_be_removed_is_recorded(logdir, tmp_path, monkeypatch):
    monkeypatch.setattr(recpipe, "audio_dir", lambda: tmp_path)
    (tmp_path / "x.webm").mkdir()  # ファイルでなくフォルダ → unlink が失敗する
    recpipe.remove_audio("x.webm", "確定した録音")
    assert "音声を消せませんでした" in log_text(logdir) and "x.webm" in log_text(logdir)
    n = len(log_text(logdir))
    recpipe.remove_audio("none.webm", "確定した録音")  # もう無いのは問題なし
    assert len(log_text(logdir)) == n


def test_extra_fields_in_reply_are_ignored_and_recorded(logdir):
    text = "右下6番の根管充填をしました"
    row = {"text": "右下6番の根管充填を行った。", "quote": "右下6番の根管充填"}
    reply = {k: [] for k in memo.KEYS}
    reply["done"] = [dict(row, confidence=0.9)]  # 行に余計な項目
    reply["comment"] = "余計な項目"               # 全体に余計な項目
    out = memo.parse_items(json.dumps(reply, ensure_ascii=False), text)
    assert len(out["done"]) == 1 and set(out["done"][0]) == {"text", "quote"}
    t = log_text(logdir)
    assert "confidence" in t and "comment" in t
    # 5つの項目が足りないときは今までどおり失敗
    short = {k: [] for k in memo.KEYS}
    short.pop("done")
    with pytest.raises(ValueError):
        memo.parse_items(json.dumps(short), text)


def test_gpu_fallback_is_recorded_and_shown(logdir, monkeypatch):
    import sys
    import types
    from app.voice import transcribe as tr

    calls = []

    class FakeModel:
        def __init__(self, name, device, compute_type, download_root=None):
            calls.append(device)
            if device == "cuda":
                raise RuntimeError("CUDA が見つかりません")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setattr(tr, "_models", {})
    tr._model("small-test")
    assert calls == ["cuda", "cpu"]
    assert tr.engine["device"] == "CPU" and "CUDA" in tr.engine["fallback_reason"]
    assert "CPU に切り替えました" in log_text(logdir)
    from fastapi.testclient import TestClient
    from app.main import app
    s = TestClient(app).get("/voice/status").json()
    assert s["device"] == "CPU" and s["fallback_reason"]


def test_mobile_start_failure_is_recorded_and_qr_says_so(logdir, monkeypatch):
    from app.routers import phone
    monkeypatch.delenv("CV_MOBILE_AUTOSTART", raising=False)
    monkeypatch.setattr(phone.links, "mobile_port", lambda: (_ for _ in ()).throw(RuntimeError("ポート設定が読めない")))
    monkeypatch.setitem(phone.mobile_status, "error", "")
    assert phone.start_mobile_server() is None
    assert "ポート設定が読めない" in phone.mobile_status["error"] and "起動" in log_text(logdir) or "準備" in log_text(logdir)
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).post("/api/phone-link", json={"appt": 1})
    assert r.status_code == 503 and "動いていません" in r.json()["detail"]
    phone.mobile_status["error"] = ""


def test_drafts_are_shown_the_same_way_sample_or_recorded(tmp_path, monkeypatch):
    """G21k-5: 見本の下書きも録音から作った下書きも同じ扱い（新しい順に全部）。種類で出し分けない。"""
    import os, subprocess, sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "CV_DATA_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    assert subprocess.run([sys.executable, str(root / "scripts" / "seed.py")], env=env, capture_output=True).returncode == 0
    probe = r'''
import json
from app.db import connect
from app.today import today
from app.views import data as D
con = connect()
a = dict(con.execute("SELECT * FROM appointments WHERE patient_id=1 AND appt_date=? AND role='doctor'", (today(),)).fetchone())
before = [x["body"] for x in D.unit_data(a, "doctor")["drafts"]]
v = con.execute("SELECT id FROM visits WHERE appointment_id=?", (a["id"],)).fetchone()[0]
con.execute("INSERT INTO drafts (patient_id, visit_id, kind, body, transcript, status, created_at) VALUES (1, ?, 'spoken_summary', '新しい下書き', '話した内容', 'draft', ?)", (v, today() + " 16:00"))
con.commit()
after = [x["body"] for x in D.unit_data(a, "doctor")["drafts"]]
print(json.dumps({"before": before, "after": after}, ensure_ascii=False))
'''
    p = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True, encoding="utf-8", cwd=root)
    assert p.returncode == 0, p.stderr[-500:]
    o = json.loads(p.stdout.strip().splitlines()[-1])
    assert o["before"] and o["after"][0] == "新しい下書き" and o["after"][1:] == o["before"]
