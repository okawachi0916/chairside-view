"""G14b: Claude につなぐ設定の試験。本物の Claude は呼ばない。"""
import json
import re
from pathlib import Path

import pytest

from app.ai import settings

ROOT = Path(__file__).resolve().parents[1]


def test_env_key_wins_over_file(monkeypatch, tmp_path):
    f = tmp_path / "app.env"
    f.write_text("CHAIRSIDE_CLAUDE_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("CHAIRSIDE_ENV_FILE", str(f))
    monkeypatch.setenv("CHAIRSIDE_CLAUDE_KEY", "env-key")
    assert settings.load_key() == "env-key"


def test_file_key_used_when_no_env(monkeypatch, tmp_path):
    f = tmp_path / "app.env"
    f.write_text("OTHER=1\nCHAIRSIDE_CLAUDE_KEY=\"file-key\"\n", encoding="utf-8")
    monkeypatch.setenv("CHAIRSIDE_ENV_FILE", str(f))
    monkeypatch.delenv("CHAIRSIDE_CLAUDE_KEY", raising=False)
    assert settings.load_key() == "file-key"


def test_anthropic_api_key_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("CHAIRSIDE_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.delenv("CHAIRSIDE_CLAUDE_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    with pytest.raises(settings.ClaudeUnavailable):
        settings.load_key()


def test_missing_key_message_has_no_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("CHAIRSIDE_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.delenv("CHAIRSIDE_CLAUDE_KEY", raising=False)
    with pytest.raises(settings.ClaudeUnavailable) as e:
        settings.load_key()
    assert "使えません" in str(e.value)


def test_redact_key(monkeypatch):
    monkeypatch.setenv("CHAIRSIDE_CLAUDE_KEY", "sk-test-secret-123")
    assert "sk-test-secret-123" not in settings.redact_key("error: bad key sk-test-secret-123")


def test_model_comes_from_config_only():
    model = json.loads((ROOT / "config" / "model.json").read_text(encoding="utf-8"))["model"]
    assert "sonnet" in model
    assert settings.load_model() == model
    # プログラムにモデル名を直接書かない
    for p in list((ROOT / "app").rglob("*.py")) + list((ROOT / "scripts").glob("*.py")):
        assert not re.search(r"claude-(sonnet|opus|haiku|fable)-\d", p.read_text(encoding="utf-8")), p


def test_no_secret_in_repo_files():
    for p in [ROOT / "config" / "model.json", ROOT / "docs" / "実API結果.md"]:
        if p.exists():
            assert not re.search(r"sk-ant-[A-Za-z0-9_-]{10,}", p.read_text(encoding="utf-8"))
