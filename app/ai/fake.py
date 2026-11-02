"""本物の Claude を呼ばない偽物の口。試験で使う。

環境変数 CHAIRSIDE_AI_FAKE_FILE にファイルの場所があるときだけ、サーバーはこの口を使う（普段は設定しない）。
ファイルは {"reply": "応答の文字", "delay_ms": 0} の形。読むたびに最新を使う。
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


class FileMouth:
    def complete(self, system, user, max_tokens):
        cfg = json.loads(Path(os.environ[ENV]).read_text(encoding="utf-8"))
        if cfg.get("delay_ms"):
            time.sleep(cfg["delay_ms"] / 1000)
        return cfg.get("reply", "")


def fake_enabled() -> bool:
    return bool(os.environ.get(ENV))
