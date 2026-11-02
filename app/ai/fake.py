"""本物の Claude や文字起こしを呼ばない偽物。試験で使う。

環境変数 CHAIRSIDE_AI_FAKE_FILE にファイルの場所があるときだけ、サーバーは偽物を使う（普段は設定しない）。
ファイルは次の形。読むたびに最新を使う。
  {"reply": "Claude の応答の文字", "delay_ms": 0,
   "transcript": "文字起こしの結果（あれば文字起こしも偽物にする）", "stt_delay_ms": 0}
"""
import json
import os
import time
from pathlib import Path

ENV = "CHAIRSIDE_AI_FAKE_FILE"


class ScriptedMouth:
    """決めた応答を返し、送られた回数と文を覚える。"""

    def __init__(self, reply="", delay_ms=0):
        self.reply, self.delay_ms = reply, delay_ms
        self.sent = []

    def complete(self, system, user, max_tokens):
        self.sent.append((system, user))
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000)
        return self.reply


def config() -> dict:
    return json.loads(Path(os.environ[ENV]).read_text(encoding="utf-8"))


class FileMouth:
    def complete(self, system, user, max_tokens):
        cfg = config()
        if cfg.get("delay_ms"):
            time.sleep(cfg["delay_ms"] / 1000)
        return cfg.get("reply", "")


def fake_enabled() -> bool:
    return bool(os.environ.get(ENV))


def fake_transcript():
    """偽物の文字起こしがあれば文字を返す。無ければ None（本物の文字起こしを使う）。"""
    if not fake_enabled():
        return None
    cfg = config()
    if "transcript" not in cfg:
        return None
    if cfg.get("stt_delay_ms"):
        time.sleep(cfg["stt_delay_ms"] / 1000)
    return cfg["transcript"]
