"""G26b: 総点検（test-gap）で見つかった試験の抜けを埋める。声のルート、写真の配信の拒否、確定済みの下書きの扱い。"""
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app

    return TestClient(app)


def test_voice_interpret_route_shape(client):
    r = client.post("/voice/interpret", json={"text": "アレルギーは？", "screen": "unit"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"kind", "text", "action", "arg", "message"}
    assert body["kind"] == "質問" and body["action"] is None
    ops = client.post("/voice/interpret", json={"text": "重要事項を全画面にして"}).json()
    assert ops["kind"] != "質問" and ops["action"]
    empty = client.post("/voice/interpret", json={}).json()  # 言葉が無くても落ちない
    assert empty["kind"] != "質問"


def test_voice_commands_route_lists_only_usable_words(client):
    words = client.get("/voice/commands").json()["words"]
    assert isinstance(words, list) and words and all(isinstance(w, str) and w for w in words)
    assert len(words) == len(set(words))


def test_keys_json_route_has_the_buttons(client):
    cfg = client.get("/config/keys.json").json()
    assert isinstance(cfg, dict) and cfg


@pytest.mark.parametrize("name", ["nothing.jpg", "..%2F..%2Fconfig%2Fmodel.json", "%2e%2e%2fapp%2Fmain.py",
                                  "..%5Capp%5Cmain.py", "photos.json", "C%3A%5CWindows%5Cwin.ini"])
def test_photo_files_rejects_unknown_and_outside_names(client, name):
    r = client.get(f"/photo-files/{name}")
    assert r.status_code in (404, 405) and b"claude-" not in r.content
