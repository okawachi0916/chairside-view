"""Claude につなぐための設定（鍵とモデル名）を読む。鍵は使うときに読み、ログにも画面にも出さない。"""
import json
import os
from pathlib import Path

KEY_NAME = "CHAIRSIDE_CLAUDE_KEY"
DEFAULT_ENV_FILE = r"C:\hackathon\secrets\app.env"
MODEL_JSON = Path(__file__).resolve().parents[2] / "config" / "model.json"


class ClaudeUnavailable(Exception):
    """鍵かモデル名が無く、Claude が使えない。メッセージは画面に出してよい文だけにする。"""


def _key_from_file(path: str) -> str:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        name, sep, value = line.partition("=")
        if sep and name.strip() == KEY_NAME:
            return value.strip().strip('"').strip("'")
    return ""


def load_key() -> str:
    """環境変数があれば先に使う。無ければ app.env の同じ名前の行。ANTHROPIC_API_KEY は見ない。"""
    key = os.environ.get(KEY_NAME, "").strip()
    if not key:
        key = _key_from_file(os.environ.get("CHAIRSIDE_ENV_FILE", DEFAULT_ENV_FILE))
    if not key:
        raise ClaudeUnavailable("Claude の鍵が見つからないため、この機能は使えません。")
    return key


def load_model(purpose: str = "") -> str:
    """config/model.json の "model" が既定。"purposes" に目的（question, memo など）があれば、その目的だけ別のモデルを使う。"""
    try:
        cfg = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
        model = cfg.get("model", "")
        by_purpose = cfg.get("purposes")
        if purpose and isinstance(by_purpose, dict) and isinstance(by_purpose.get(purpose), str):
            model = by_purpose[purpose].strip() or model
    except (OSError, ValueError, AttributeError):
        model = ""
    if not model:
        raise ClaudeUnavailable("Claude のモデル名が設定されていないため、この機能は使えません。")
    return model


def auto_summary() -> bool:
    """録音を止めたあと、自動で要約まで進めるか。既定は false（文字起こしまで）。環境変数 CHAIRSIDE_AUTO_SUMMARY=1/0 が先。"""
    env = os.environ.get("CHAIRSIDE_AUTO_SUMMARY", "").strip().lower()
    if env:
        return env in ("1", "true", "yes", "on")
    try:
        return json.loads(MODEL_JSON.read_text(encoding="utf-8")).get("auto_summary") is True
    except (OSError, ValueError, AttributeError):
        return False


def redact_key(text: str) -> str:
    """文字列の中に鍵があれば伏せる。ログや画面に出す前に通す。"""
    try:
        key = load_key()
    except ClaudeUnavailable:
        return text
    return text.replace(key, "[鍵]")
