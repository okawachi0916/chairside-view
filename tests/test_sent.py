"""G26: Claude へ送った文を見る画面 /sent の試験。下書きと質問の両方が出ること、元の名前が画面に出ないこと。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import ask as ask_mod
from app.ai import fixtalk, memo
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway, sensitive_from_db

ROOT = Path(__file__).resolve().parents[1]
NAME, KANA = "見本 花子", "ミホンハナコ"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    d = tmp_path_factory.mktemp("sent")
    e = {**os.environ, "CV_DATA_DIR": str(d), "PYTHONIOENCODING": "utf-8"}
    assert subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], env=e, capture_output=True).returncode == 0
    old = os.environ.get("CV_DATA_DIR")
    os.environ["CV_DATA_DIR"] = str(d)
    from app.db import connect
    from app.main import app

    con = connect()
    sens = sensitive_from_db(con)
    pid = con.execute("SELECT id FROM patients WHERE chart_no = '0123'").fetchone()["id"]
    # 送信: 質問、下書き（聞き違いの直し→5つに分ける）。どれも名前を入れて送る
    gw = Gateway(mouth=ScriptedMouth('{"result":"none"}'))
    ask_mod.answer(f"{NAME}さんのペニシリンの記録は？", con, pid, gw, quick=False)
    talk = f"{NAME}さんの診療です。今日は右下6番の根管充填をしました。"
    reply = json.dumps({**{k: [] for k in memo.KEYS}, "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"}]},
                       ensure_ascii=False)
    fixtalk.polish(talk, sens, Gateway(mouth=ScriptedMouth(reply)))
    memo.organize(talk, sens, Gateway(mouth=ScriptedMouth(reply)))
    yield {"client": TestClient(app), "dir": d, "con": con}
    con.close()
    if old is None:
        os.environ.pop("CV_DATA_DIR", None)
    else:
        os.environ["CV_DATA_DIR"] = old


def test_question_and_draft_sends_both_appear(env):
    r = env["client"].get("/sent")
    assert r.status_code == 200
    page = r.text
    assert "data-purpose='question'" in page and "data-purpose='memo'" in page and "data-purpose='polish'" in page
    assert "質問" in page and "下書き" in page and "清書" in page
    assert "ペニシリンの記録は" in page and "右下6番の根管充填をしました" in page  # 送った文の中身


def test_masked_parts_are_colored_and_real_names_never_shown(env):
    page = env["client"].get("/sent").text
    assert "<mark class='masked'>[" in page  # 伏字に色
    body = page.split("<main")[1]
    assert "見本" not in body and "花子" not in body and "ミホン" not in body


def test_unmasked_old_log_lines_are_masked_before_showing(env):
    f = Path(env["dir"]) / "sent_log" / "2099-01-01.jsonl"
    f.write_text(json.dumps({"time": "2099-01-01T00:00:00", "purpose": "memo", "system": "指示",
                             "user": f"{NAME}さん ミホンハナコ"}, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        body = env["client"].get("/sent").text.split("<main")[1]
        assert "見本" not in body and "花子" not in body and "ミホン" not in body
        assert "<mark class='masked'>[" in body
    finally:
        f.unlink()


def test_newest_first_and_html_is_escaped(env):
    d = Path(env["dir"]) / "sent_log"
    old, new = d / "2098-01-01.jsonl", d / "2098-01-02.jsonl"
    old.write_text(json.dumps({"time": "2098-01-01T00:00:00", "purpose": "question", "system": "", "user": "古い送信"}) + "\n", encoding="utf-8")
    new.write_text(json.dumps({"time": "2098-01-02T00:00:00", "purpose": "question", "system": "",
                               "user": "新しい送信<script>alert(1)</script>"}) + "\n" + "壊れた行\n", encoding="utf-8")
    try:
        page = env["client"].get("/sent").text
        assert page.index("新しい送信") < page.index("古い送信")
        assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    finally:
        old.unlink()
        new.unlink()


def test_empty_log_and_limit(env, tmp_path, monkeypatch):
    monkeypatch.setenv("CV_DATA_DIR", str(tmp_path))
    from app.routers import sent

    assert sent.read_entries() == []
    assert env["client"].get("/sent", params={"n": 1}).status_code == 200
    page = env["client"].get("/sent").text
    assert "まだ Claude へ送った文はありません" in page

