"""話した文字の聞き違いを、文脈から正しい文に整える（清書）。

文字起こし（Whisper）は聞き取りだけ。聞き取りのすぐ後に、Claude が「その患者様の今日の予定・治療計画・直近の治療歴」と
歯科の言葉の一覧を見て、正しい字に直した全文を返す。画面に出すのは清書。聞き取ったままの文も残す（呼ぶ側が保存する）。

Claude に頼むこと: 直した全文 text、直した所 fixes（元→直し）、迷う言葉 doubts。読みが違っても、流れから明らかなら直してよい。
プログラムの安全策は2つだけ:
- 歯の番号・数字・日付・薬の量は変えない。聞き取りと清書で数字が違えば、清書を使わず聞き取りのまま出す。
- 話していない内容を足さない。清書が聞き取りより大きく長くなったら（1.3倍を超えたら）、聞き取りのまま出す。
清書が失敗したり形が崩れたりしたときも、聞き取りのままで先へ進み、理由を note に返す（呼ぶ側が画面に出す）。
書き方をそろえる決まり（TEK→TeC など）は config/dental_terms.json の spellings で、Claude を通さずに行う（表記の統一）。
config の readings は、置き換えの一覧ではなく「こういう聞き違いが起きる」という例として Claude に渡す。
"""
import difflib
import html
import json
import re
import unicodedata
from pathlib import Path

from app.ai.gateway import Gateway

CONFIG = Path(__file__).resolve().parents[2] / "config" / "dental_terms.json"
MAX_TERMS = 80          # 文字起こしのヒント（initial_prompt）に入れる語。多いと逆効果
MAX_RATIO = 1.3         # 清書が聞き取りよりこれより長くなったら使わない
MAX_FIXES = 60
USER_PREFIX = "聞き取りの文:" + chr(10)

NOTE_FAILED = "清書できませんでした。聞き取りのまま出しています"
NOTE_DIGITS = "清書で数字が変わったため、聞き取りのまま出しています"
NOTE_LONG = "清書が聞き取りより長くなったため、聞き取りのまま出しています"

SYSTEM = (
    "あなたは歯科医院の記録の清書係です。次の文は、歯科の診療中に、歯科医師（または歯科衛生士）が患者様について話した内容を、"
    "音声認識で文字にしたものです。歯科の診療に関わる話だけをしています。音声認識には聞き違いがあります。\n"
    "やること:\n"
    "- 話の流れと歯科の言葉から、聞き違いを正しい字に直した全文を text に返します。"
    "読みが違う言葉でも、話の流れから明らかなら直してよいです。\n"
    "- 話していない内容を足しません。言い回しを整えすぎず、話した順と言葉をなるべく残します。文を短くしたり、まとめたりしません。\n"
    "- 歯の番号、数字、日付、薬の量は変えません。\n"
    "- 迷う言葉は直さずに text へそのまま残し、その言葉を doubts に入れます。\n"
    "- 直した所は fixes に入れます。from は聞き取りの文にある言葉、to は直した言葉です。\n"
    "- 診断や治療の提案はしません。直す所が無ければ、text は聞き取りの文のままにします。仮歯は TeC と書きます。\n"
    "{context}"
    "歯科の言葉の一覧: {glossary}\n"
    "聞き違いの例: {examples}\n"
    "次のJSONだけを返します。説明文は付けません。\n"
    '{"text":"直した全文","fixes":[{"from":"…","to":"…"}],"doubts":["…"]}'
)


def load_config() -> dict:
    """読めないときは空の設定。その場合はヒントも一覧も渡さない（文字起こしも清書も動く）。"""
    try:
        d = json.loads(CONFIG.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _words(key: str) -> list:
    return [x for x in load_config().get(key, []) if isinstance(x, str) and x.strip()]


def terms() -> list:
    return _words("terms")[:MAX_TERMS]


def glossary() -> list:
    """清書で Claude に渡す歯科の言葉。terms と重なるものは1つにする。"""
    seen, out = set(), []
    for w in terms() + _words("glossary"):
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def examples() -> str:
    """聞き違いの例（config の readings）。置き換えの一覧としては使わない。"""
    rd = load_config().get("readings")
    if not isinstance(rd, dict):
        return ""
    pairs = []
    for good, bads in rd.items():
        for bad in bads if isinstance(bads, list) else []:
            if isinstance(good, str) and isinstance(bad, str) and bad and bad != good:
                pairs.append(f"{bad}→{good}")
    return "、".join(pairs)


def initial_prompt() -> str:
    """ボタン1の録音の文字起こしにだけ渡す。歯科の短い一文と主な語（聞き取りのヒント）。"""
    cfg = load_config()
    sentence = cfg.get("sentence", "") if isinstance(cfg.get("sentence"), str) else ""
    words = terms()
    if not sentence and not words:
        return ""
    return (sentence + "、".join(words) + "。").strip()


# ---- 清書 ----

_NUM = re.compile(r"[0-9〇一二三四五六七八九十百千万]")


def _digits(s: str) -> str:
    return "".join(_NUM.findall(unicodedata.normalize("NFKC", s or "")))


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))


def parse_polish(raw: str, transcript: str) -> dict:
    """Claude の応答（JSON）から {text, fixes, doubts} を取り出す。形が違えば ValueError。"""
    s = (raw or "").strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    if m:
        s = m.group(1)
    try:
        obj = json.loads(s)
    except ValueError:
        raise ValueError("応答の形が違います") from None
    if not isinstance(obj, dict) or not isinstance(obj.get("text"), str) or not obj["text"].strip():
        raise ValueError("応答の形が違います")
    text = obj["text"].strip()
    fixes, seen = [], set()
    for r in obj.get("fixes") if isinstance(obj.get("fixes"), list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("from"), str) or not isinstance(r.get("to"), str):
            continue                       # 形が違う直しは、その1つだけ捨てる（清書の本文は使う）
        a, b = r["from"].strip(), r["to"].strip()
        if a and b and a != b and a not in seen and a in transcript and b in text:   # 画面の「元→直し」と、本文・聞き取りが合うものだけ
            seen.add(a)
            fixes.append({"from": a, "to": b, "by": "claude"})
    doubts = []
    for w in obj.get("doubts") if isinstance(obj.get("doubts"), list) else []:
        if isinstance(w, str) and w.strip() and w.strip() in text and w.strip() not in doubts:
            doubts.append(w.strip())
    return {"text": text, "fixes": fixes[:MAX_FIXES], "doubts": doubts[:30]}


_RUN = re.compile(r"[一-鿿々〆]+|[ぁ-ゖ]+|[ァ-ヺー]+|[A-Za-zＡ-Ｚａ-ｚ]+|[0-9０-９]+|.", re.S)


def diff_fixes(transcript: str, polished: str) -> list:
    """聞き取りと清書の違いを、字の種類（漢字・ひらがな・カタカナ…）のまとまりごとに数えて、「元→直し」にする。
    Claude が直したのに fixes に入れ忘れた所を、画面の「直した聞き違い」の欄と下線から落とさないため。"""
    a, b = _RUN.findall(transcript), _RUN.findall(polished)
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "replace":
            continue
        src, dst = "".join(a[i1:i2]).strip(), "".join(b[j1:j2]).strip()
        if src and dst and src != dst and re.search(r"[^\W_]", src) and re.search(r"[^\W_]", dst):
            out.append({"from": src, "to": dst, "by": "claude"})
    return out


def with_missing_fixes(transcript: str, polished: str, fixes: list) -> list:
    """Claude が出した直しに、清書で変わっているのに載っていない所を足す。"""
    out = list(fixes)
    for d in diff_fixes(transcript, polished):
        covered = any((d["from"] in f["from"] or f["from"] in d["from"]) and (d["to"] in f["to"] or f["to"] in d["to"]) for f in out)
        if not covered and d["from"] not in [f["from"] for f in out]:
            out.append(d)
    return out[:MAX_FIXES]


def unsafe_reason(transcript: str, polished: str) -> str:
    """清書を使ってはいけない理由。使ってよければ空。数字を変えない・話していない内容を足さない、の2つだけ。"""
    if _digits(transcript) != _digits(polished):
        return NOTE_DIGITS
    if len(_squash(polished)) > len(_squash(transcript)) * MAX_RATIO:
        return NOTE_LONG
    return ""


def _spelling_rules() -> list:
    sp = load_config().get("spellings")
    rules = []
    if isinstance(sp, dict):
        for good, bads in sp.items():
            for bad in bads if isinstance(bads, list) else []:
                if isinstance(good, str) and isinstance(bad, str) and bad and bad != good:
                    rules.append((bad, good))
    return sorted(rules, key=lambda x: len(x[0]), reverse=True)


def _boundary(bad: str) -> re.Pattern:
    """同じ種類の文字に挟まれた中（テックス の テック など）は直さない。"""
    if bad.isascii() or re.fullmatch(r"[Ａ-Ｚａ-ｚ]+", bad):
        left, right = r"(?<![A-Za-zＡ-Ｚａ-ｚ0-9])", r"(?![A-Za-zＡ-Ｚａ-ｚ0-9])"
    elif re.fullmatch(r"[ァ-ヶー]+", bad):
        left, right = r"(?<![ァ-ヶー])", r"(?![ァ-ヶー])"
    else:
        left = right = ""
    return re.compile(left + re.escape(bad) + right)


def normalize_spellings(text: str):
    """書き方をそろえる（TEK→TeC など。表記の統一）。戻り値: (直した文字, 直した一覧)。"""
    changes = []
    for bad, good in _spelling_rules():
        pat = _boundary(bad)
        if pat.search(text):
            text = pat.sub(good, text)
            changes.append({"from": bad, "to": good, "by": "rule"})
    return text, changes


def polish(transcript: str, sens, gateway: Gateway, context: str = "", timeout: float = 0) -> dict:
    """聞き取りの文を清書する。戻り値: {text, polished, fixes, doubts, note}。
    text は画面に出す文（清書、使えないときは聞き取りのまま）。失敗しても例外にしない（要約まで止めない）。"""
    transcript = (transcript or "").strip()
    out = {"text": transcript, "polished": False, "fixes": [], "doubts": [], "note": ""}
    if not transcript:
        return out
    system = (SYSTEM.replace("{context}", f"その患者様の情報（話の聞き違いを直す手がかり。ここにある内容を text に足さない）:{chr(10)}{context}{chr(10)}" if context else "")
              .replace("{glossary}", "、".join(glossary())).replace("{examples}", examples()))
    try:
        reply = gateway.send(USER_PREFIX + transcript, sens, system=system, max_tokens=4000, purpose="polish", timeout=timeout)
        got = parse_polish(reply.text, transcript)   # 名前を戻したあとの文字で照らす
    except Exception:  # noqa: BLE001  清書の失敗で、記録の流れを止めない
        out["note"] = NOTE_FAILED
        out["text"], rule = normalize_spellings(transcript)
        out["fixes"] = rule
        return out
    why = unsafe_reason(transcript, got["text"])
    if why:
        out["note"] = why
        out["text"], rule = normalize_spellings(transcript)
        out["fixes"] = rule
        return out
    text, rule = normalize_spellings(got["text"])
    fixes = with_missing_fixes(transcript, got["text"], got["fixes"])
    out.update(text=text, polished=True, fixes=fixes + rule, doubts=[d for d in got["doubts"] if d in text])
    return out


def marked_html(text: str, fixes: list, doubts: list) -> str:
    """清書の本文を画面の HTML にする。直した言葉に下線（u.pf-fix）、迷う言葉に印（mark.pf-doubt）。"""
    spans = []
    for kind, words in (("fix", [f["to"] for f in fixes]), ("doubt", doubts)):
        for w in words:
            i = text.find(w) if w else -1
            while i >= 0:
                spans.append((i, i + len(w), kind))
                i = text.find(w, i + len(w))
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out, pos = [], 0
    for a, b, kind in spans:
        if a < pos:
            continue                       # 重なる分は先に出した方だけ
        out.append(html.escape(text[pos:a]))
        tag = "u" if kind == "fix" else "mark"
        out.append(f'<{tag} class="pf-{kind}">{html.escape(text[a:b])}</{tag}>')
        pos = b
    out.append(html.escape(text[pos:]))
    return "".join(out)


def finish_text(text: str) -> str:
    """カルテに書く1文の形をそろえる。句読点で終え、仮歯の書き方をそろえる。"""
    text, _ = normalize_spellings((text or "").strip())
    if text and text[-1] not in "。！？":
        text += "。"
    return text
