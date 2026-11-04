"""本物の Claude や文字起こしを呼ばない偽物。試験で使う。

環境変数 CHAIRSIDE_AI_FAKE_FILE にファイルの場所があるときだけ、サーバーは偽物を使う（普段は設定しない）。
ファイルは次の形。読むたびに最新を使う。
  {"reply": "Claude の応答の文字", "polish_reply": "清書の応答（JSON）。無ければ「直す所なし」", "delay_ms": 0,
   "transcript": "文字起こしの結果（あれば文字起こしも偽物にする）", "stt_delay_ms": 0}
"""
import json
import os
import time
from pathlib import Path

ENV = "CHAIRSIDE_AI_FAKE_FILE"
USER_PREFIX = "聞き取りの文:" + chr(10)  # 清書の送信の頭（fixtalk と同じ）


def talk_of(user: str) -> str:
    return user[len(USER_PREFIX):] if user.startswith(USER_PREFIX) else user


def echo_polish(user: str) -> str:
    """清書の偽物の既定: 聞き取りの文をそのまま返す（直す所なし）。"""
    return json.dumps({"text": talk_of(user), "fixes": [], "doubts": []}, ensure_ascii=False)


class ScriptedMouth:
    """決めた応答を返し、送られた回数と文を覚える。清書の送信（purpose=polish）は polish_reply を返し、polish_sent に覚える
    （sent の数は、5つに分ける送信など、ほかの送信だけ数える）。"""

    wants_purpose = True

    def __init__(self, reply="", delay_ms=0, polish_reply=None):
        self.reply, self.delay_ms, self.polish_reply = reply, delay_ms, polish_reply
        self.sent = []
        self.polish_sent = []

    def complete(self, system, user, max_tokens, purpose=""):
        if purpose == "polish":
            self.polish_sent.append((system, user))
            if callable(self.polish_reply):  # 聞き取りの文を受け取って応答を作る（試験用）
                return self.polish_reply(talk_of(user))
            return echo_polish(user) if self.polish_reply is None else self.polish_reply
        self.sent.append((system, user))
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000)
        return self.reply


def config() -> dict:
    return json.loads(Path(os.environ[ENV]).read_text(encoding="utf-8"))


class FileMouth:
    wants_purpose = True

    def complete(self, system, user, max_tokens, purpose=""):
        cfg = config()
        if purpose == "polish":  # 清書の送信。ファイルに polish_reply が無ければ「直す所なし」
            return cfg["polish_reply"] if "polish_reply" in cfg else echo_polish(user)
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
