"""聞き違いの表（config/mishear.json）を読み、声の操作の言葉に直した「別の読み」の候補を作る（G14o）。

使う場面は 1 か所だけ: app/voice/interpret.py が操作の言葉（config/commands.json）と照らし合わせるとき。
診療の録音の文字起こし・話した内容の整理・下書き・歯科の言葉への聞き違い直し（app/ai）では使わない。
Claude は使わない。表で置き換えるだけ。元の聞き取りの文が先に照合され、合わなかったときだけここの候補を試す。

表は3つ。スタッフが「この聞こえ方も 7 番」と足せるよう、1行が {聞こえ方, 正しくは, 出どころ} の形。
- 番号の言い方: 「なな」「七」→ 7 のような、数の聞こえ方
- 番の聞こえ方: 「ば」「バン」「晩」→ 番 のような、「番」の聞こえ方
- 操作の言葉の聞こえ方: 「確大」→ 拡大 のような、操作の言葉の聞こえ方（場所: どこでも / 語尾 / 全体）
番号は「数の言い方 + 番の聞こえ方」がひと続きのときだけ直す。「いち」だけ・「ば」だけでは動かさない。
"""
import json
import re
import unicodedata
from pathlib import Path

TABLE = Path(__file__).resolve().parents[2] / "config" / "mishear.json"
_cache = {"mtime": None, "data": None}


def _kata_to_hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def _compile(raw: dict) -> dict:
    nums: dict[str, str] = {}
    for r in raw.get("番号の言い方", []):
        nums[_norm(r["聞こえ方"])] = str(r["正しくは"])
    bans = sorted({_norm(r["聞こえ方"]) for r in raw.get("番の聞こえ方", [])} | {"番"}, key=len, reverse=True)
    num_alt = "|".join(re.escape(k) for k in sorted(nums, key=len, reverse=True))
    ban_alt = "|".join(re.escape(b) for b in bans)
    # 数 + 番 がひと続きの所だけ。数は表の言い方か、算用数字/漢数字
    ban_rx = re.compile(rf"(?P<n>{num_alt}|[0-9]+)(?:{ban_alt})(?![0-9])")
    ops = [(_norm(r["聞こえ方"]), _norm(r["正しくは"]), r.get("場所", "どこでも")) for r in raw.get("操作の言葉の聞こえ方", [])]
    ops.sort(key=lambda o: len(o[0]), reverse=True)
    return {"nums": nums, "ban_rx": ban_rx, "ops": ops}


def _table() -> dict:
    """表は読み直しを避ける（速さのため）。ファイルが変わったときだけ読み直す。無ければ空の表。"""
    try:
        m = TABLE.stat().st_mtime_ns
    except OSError:
        return {"nums": {}, "ban_rx": None, "ops": []}
    if _cache["mtime"] != m:
        _cache["data"] = _compile(json.loads(TABLE.read_text(encoding="utf-8")))
        _cache["mtime"] = m
    return _cache["data"]


def _fix_numbers(s: str, t: dict) -> str:
    if not t["ban_rx"]:
        return s
    return t["ban_rx"].sub(lambda m: t["nums"].get(m.group("n"), m.group("n")) + "番", s)


def _fix_ops(s: str, t: dict) -> str:
    """直した結果にまた当てはまる行があるので、変わらなくなるまで（最大3回）くり返す。"""
    for _ in range(3):
        n = _fix_ops_once(s, t)
        if n == s:
            break
        s = n
    return s


def _fix_ops_once(s: str, t: dict) -> str:
    for heard, right, where in t["ops"]:
        if where == "全体":
            if s == heard:
                s = right
        elif where == "語尾":
            if s.endswith(heard):
                s = s[: -len(heard)] + right
        elif heard in s:
            s = s.replace(heard, right)
    return s


def variants(s: str) -> list:
    """聞き取った文（句読点を外したもの）から、聞き違いを直した別の読みを作る。元の文は含めない。"""
    t = _table()
    out = []

    def add(v):
        if v and v != s and v not in out:
            out.append(v)

    k = _kata_to_hira(s)  # カタカナで返ってきた聞こえ方も、ひらがなの言葉の表と照らす
    for base in (s, k):
        o = _fix_ops(base, t)
        for v in (base, o):
            add(v)
            add(_fix_numbers(v, t))
    return out
