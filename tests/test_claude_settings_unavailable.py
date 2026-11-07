"""鍵が無い・モデル名が空のとき、機能だけが「使えません」になる（起動は止まらない）。"""
import json

import pytest

from app.ai import settings
from app.ai.settings import ClaudeUnavailable


def test_no_key_raises_unavailable(monkeypatch, tmp_path):
    monkeypatch.delenv(settings.KEY_NAME, raising=False)
    monkeypatch.setenv("CHAIRSIDE_ENV_FILE", str(tmp_path / "none.env"))
    with pytest.raises(ClaudeUnavailable) as e:
        settings.load_key()
    assert "使えません" in str(e.value)


def test_empty_model_raises_unavailable(monkeypatch, tmp_path):
    f = tmp_path / "model.json"
    f.write_text(json.dumps({"model": ""}), encoding="utf-8")
    monkeypatch.setattr(settings, "MODEL_JSON", f)
    with pytest.raises(ClaudeUnavailable) as e:
        settings.load_model()
    assert "使えません" in str(e.value)
    monkeypatch.setattr(settings, "MODEL_JSON", tmp_path / "missing.json")
    with pytest.raises(ClaudeUnavailable):
        settings.load_model("question")
