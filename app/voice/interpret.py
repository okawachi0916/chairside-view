"""聞き取った言葉を 操作 / 質問 / 無関係 / 聞き取り失敗 に分け、操作なら config/commands.json の表で照合する。
Claude は使わない。言った全体が表の言葉に合うときだけ動かす。"""
import functools
import itertools
import json
import re
import unicodedata
from pathlib import Path

COMMANDS = Path(__file__).resolve().parents[2] / "config" / "commands.json"

OP, QUESTION, UNRELATED, FAILED = "操作", "質問", "無関係", "聞き取り失敗"
MSG_QUESTION = "まだ答えられません"
MSG_RETRY = "もう一度お願いします"
FILLERS = ["あのー", "あの", "えっと", "えーっと", "えーと", "ええと", "えー", "ええ", "その", "そのー", "あー", "ああ", "うーん", "うん", "んー", "まあ", "ま"]
_PUNCT = re.compile(r"[\s。、，．,.！!？?「」『』（）()・…~〜]+")
_BARE_NUMBER = re.compile(r"[0-9]+|[一二三四五六七八九十]")  # 番号だけの言葉（長さ1でも聞き取り失敗にしない）
_KANJI = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


_cache = {"mtime": None, "rows": None}


def load_table():
    """表は読み直しを避ける（速さのため）。ファイルが変わったときだけ読み直す。"""
    m = COMMANDS.stat().st_mtime_ns
    if _cache["mtime"] != m:
        _cache["rows"] = json.loads(COMMANDS.read_text(encoding="utf-8"))
        _cache["mtime"] = m
    return _cache["rows"]


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "")
    s = _PUNCT.sub("", s)
    return s


def _suru(s: str) -> str:
    """語尾の「する」は「して」と同じに扱う。"""
    return s[:-2] + "して" if s.endswith("する") else s


def to_number(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    if s and all(c in _KANJI or c == "十" for c in s):
        if s == "十":
            return 10
        if s.startswith("十"):
            return 10 + _KANJI.get(s[1:], 0)
        if "十" in s:
            a, _, b = s.partition("十")
            return _KANJI[a] * 10 + (_KANJI[b] if b else 0)
        return _KANJI[s] if len(s) == 1 else None
    return None


_PART = r"(\{\w+\}|\([^()]*\))"


def expand(word: str) -> list:
    """言葉の中の (あ|い|) の選び方を全部ならべる。{n1} などの欄はそのまま残す。"""
    parts = re.split(_PART, word)
    choices = [p[1:-1].split("|") if p.startswith("(") else [p] for p in parts]
    return ["".join(c) for c in itertools.product(*choices)]


@functools.lru_cache(maxsize=None)
def _pattern(word: str) -> re.Pattern:
    """言葉の書き方: {n1} は数字の欄、(あ|い|) はどれか1つ（空も可）。"""
    rx = ""
    pieces = re.split(_PART, unicodedata.normalize("NFKC", word))
    pieces[-1] = _suru(pieces[-1])
    for p in pieces:
        if p.startswith("{"):
            rx += f"(?P<{p[1:-1]}>[0-9]+|[一二三四五六七八九十]+)"
        elif p.startswith("("):
            rx += "(?:" + "|".join(re.escape(_norm(x)) for x in p[1:-1].split("|")) + ")"
        else:
            rx += re.escape(_norm(p))
    return re.compile(rx)


def _failed(raw: str, s: str) -> bool:
    if len(s) < 2:
        return True
    for k in range(1, len(s) // 2 + 1):  # 同じ言葉のくり返し
        if len(s) % k == 0 and s == s[:k] * (len(s) // k):
            return True
    rest = s
    for f in sorted(FILLERS, key=len, reverse=True):
        rest = rest.replace(f, "")
    return rest == ""


def _is_question(raw: str, s: str) -> bool:
    if "？" in raw or "?" in raw:
        return True
    if re.search(r"(は|か|教えて|見せて)$", s):
        return True
    return bool(re.search(r"何|いつ|どこ|どの", s))


def interpret(text: str, screen: str = "unit") -> dict:
    raw = unicodedata.normalize("NFKC", text or "")
    s = _norm(raw)
    out = {"kind": UNRELATED, "text": text or "", "action": None, "arg": None, "message": MSG_RETRY}
    if not _BARE_NUMBER.fullmatch(s) and _failed(raw, s):
        out["kind"] = FAILED
        return out
    s2 = _suru(s)
    for row in load_table():
        if screen not in row["使える画面"]:
            continue
        m = _pattern(row["言葉"]).fullmatch(s2)
        if not m:
            continue
        res = dict(row["結果"])
        out["kind"] = OP
        out["message"] = res.get("message", "")
        if row["状態"] == "使える" and res.get("action"):
            nums = {k: to_number(v) for k, v in m.groupdict().items()}
            out["action"] = res["action"]
            out["arg"] = res.get("arg")
            if nums:
                out["numbers"] = [nums[k] for k in sorted(nums)]
        else:
            out["message"] = res.get("message", "まだ開けません")
        out["word"] = row["言葉"]
        return out
    if _is_question(raw, s):
        out.update(kind=QUESTION, message=MSG_QUESTION)
    return out
