"""話した文字の聞き違いを直す。文字起こしの聞き違い（根管充填→根幹重点 など）が、そのまま下書きに入らないようにする。

Claude が返すのは {"from","to","from_yomi","to_yomi"} の一覧だけ。置き換えはこのプログラムが行う。
- from は、話の文字にそのまま在る言葉だけを認める。無いものは捨てる。
- 読み（ひらがな）が同じ、または1字だけ違うときだけ使う。読みが違う言葉への直し（副髄→抜髄 など）は捨てる。
  読みが返らない・形が違う直しも、その1つだけ捨てる（文字起こしは止めない）。
- 部位の番号・数字・日付・薬の量（数字）は直さない。from と to の数字は同じでなければ捨てる。
- 言い換え・言葉を足す直しは認めない（to の長さを from から離れ過ぎないようにする）。
- 直したあとの文字とは別に、話したままの文字を残す（呼ぶ側が保存する）。
書き方をそろえる決まり（TEK→TeC など）は config/dental_terms.json の spellings で、Claude を通さずに行う。
"""
import json
import re
import unicodedata
from pathlib import Path

from app.ai.gateway import Gateway

CONFIG = Path(__file__).resolve().parents[2] / "config" / "dental_terms.json"
MAX_FIXES = 30
MAX_TERMS = 80

SYSTEM = (
    "あなたは歯科医院の記録の校正係です。次の文は、歯科の治療中に歯科医師が話した内容を音声認識で文字にしたもので、聞き違いがあります。\n"
    "直してよいのは、同じか近い読みの歯科の言葉への聞き違いだけです。\n"
    "決まり:\n"
    "- 言い換えません。言葉を足しません。文を直しません。迷う所は直しません。\n"
    "- 部位の番号（右下6番など）、数字、日付、薬の量は、絶対に直しません。\n"
    "- from は、話の文字にある言葉をそのまま写します（一続きで、20字以内）。\n"
    "- to は、from と同じ読みの言葉にします。読みが違う言葉には替えません。同じ読みの言葉が見つからなければ直しません。\n"
    "- from_yomi と to_yomi に、それぞれの読みをひらがなで書きます。\n"
    "- 聞き違いが無ければ、空の配列 [] を返します。\n"
    "- 歯科の言葉の例: {terms}\n"
    "- 聞き違いの例: 根幹重点→根管充填、肺脳→排膿、次第蓄造→支台築造、副髄→覆髄（抜髄ではない。読みが違う）\n"
    "次のJSONの配列だけを返します。説明文は付けません。\n"
    '[{"from":"…","to":"…","from_yomi":"…","to_yomi":"…"}]'
)


def load_config() -> dict:
    """読めないときは空の設定。その場合は初期の文も語も渡さない（文字起こしは動く）。"""
    try:
        d = json.loads(CONFIG.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def terms() -> list:
    t = [x for x in load_config().get("terms", []) if isinstance(x, str) and x.strip()]
    return t[:MAX_TERMS]


def initial_prompt() -> str:
    """ボタン1の録音の文字起こしにだけ渡す。歯科の短い一文と主な語。"""
    cfg = load_config()
    sentence = cfg.get("sentence", "") if isinstance(cfg.get("sentence"), str) else ""
    words = terms()
    if not sentence and not words:
        return ""
    return (sentence + "、".join(words) + "。").strip()


_NUM = re.compile(r"[0-9〇一二三四五六七八九十百千万]")
_SMALL = str.maketrans("ぁぃぅぇぉっゃゅょゎ", "あいうえおつやゆよわ")


def _kana(s: str) -> str:
    """読みの比べ用。カタカナはひらがなにし、空白を除く。"""
    s = unicodedata.normalize("NFKC", s or "")
    s = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)
    return re.sub(r"\s+", "", s)


def _plain(s: str) -> str:
    """濁点・半濁点・小さい字・長音の違いを無くした形。"""
    s = unicodedata.normalize("NFD", _kana(s))
    s = "".join(c for c in s if c not in "゙゚").translate(_SMALL)
    return s.replace("ー", "")


def _dist_le1(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i + 1:] or a[i:] == b[i + 1:] or a[i + 1:] == b[i:]


def same_reading(a: str, b: str) -> bool:
    """読みが同じ、または1字だけ違う（濁点・長音・小さい字の違いは同じ読みとみなす）。ひらがなだけの読みに限る。"""
    ka, kb = _kana(a), _kana(b)
    if not ka or not kb or not re.fullmatch(r"[ぁ-ゖー]+", ka) or not re.fullmatch(r"[ぁ-ゖー]+", kb):
        return False
    return _plain(ka) == _plain(kb) or _dist_le1(ka, kb)


def _digits(s: str) -> str:
    return "".join(_NUM.findall(unicodedata.normalize("NFKC", s)))


def parse_fixes(raw: str, transcript: str) -> list:
    """Claude の応答から、使ってよい直しだけ取り出す。形が違えば ValueError。"""
    s = (raw or "").strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    if m:
        s = m.group(1)
    try:
        obj = json.loads(s)
    except ValueError:
        raise ValueError("応答の形が違います") from None
    if not isinstance(obj, list) or len(obj) > 200:
        raise ValueError("応答の形が違います")
    out, seen = [], set()
    for r in obj:
        if not isinstance(r, dict):
            raise ValueError("応答の形が違います")
        if not all(isinstance(r.get(k), str) for k in ("from", "to", "from_yomi", "to_yomi")):
            continue                       # 読みが無い・形が違う直しは、その1つだけ捨てる
        a, b = r["from"].strip(), r["to"].strip()
        if not same_reading(r["from_yomi"], r["to_yomi"]):
            continue                       # 読みが違う言葉には替えない（副髄→抜髄 など）
        if not a or not b or a == b or a in seen:
            continue
        if len(a) < 2 or len(a) > 20 or len(b) > len(a) * 2 + 2:
            continue                       # 短過ぎる（1字の置き換え）、長過ぎる、言葉を足す直しは認めない
        if a not in transcript:
            continue                       # 話の文字に無い言葉は直さない
        if _digits(a) != _digits(b):
            continue                       # 数字・番号・日付・薬の量は直さない
        if re.search(r"[\n、。，．,.！!？?]", b):
            continue
        seen.add(a)
        out.append({"from": a, "to": b, "by": "claude"})
    return out[:MAX_FIXES]


def apply_fixes(transcript: str, fixes: list) -> str:
    """長い from から順に、話の文字を置き換える。"""
    text = transcript
    for f in sorted(fixes, key=lambda x: len(x["from"]), reverse=True):
        text = text.replace(f["from"], f["to"])
    return text


def _spelling_rules() -> list:
    cfg = load_config()
    rules = []
    for key in ("spellings", "readings"):   # 書き方をそろえる決まりと、読みが同じ聞き違いの決まり
        sp = cfg.get(key)
        if not isinstance(sp, dict):
            continue
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
    """書き方をそろえる。戻り値: (直した文字, 直した一覧)。"""
    changes = []
    for bad, good in _spelling_rules():
        pat = _boundary(bad)
        if pat.search(text):
            text = pat.sub(good, text)
            changes.append({"from": bad, "to": good, "by": "rule"})
    return text, changes


def fix_transcript(transcript: str, sens, gateway: Gateway):
    """聞き違いを直す。戻り値: (直した文字, 直した一覧)。送るのは送信口だけ（伏字つき）。"""
    reply = gateway.send(f"話した内容:\n{transcript}", sens,
                         system=SYSTEM.replace("{terms}", "、".join(terms())), max_tokens=2000, purpose="fix")
    fixes = parse_fixes(reply.text, transcript)       # 名前を戻したあとの文字で、話した文字と照らす
    bads = [b for b, _ in _spelling_rules()]
    fixes = [f for f in fixes if not any(b in f["from"] or f["from"] in b for b in bads)]  # 決まりにある言葉は、決まりで直す
    text = apply_fixes(transcript, fixes)
    text, rule = normalize_spellings(text)
    return text, fixes + rule


def finish_text(text: str) -> str:
    """カルテに書く1文の形をそろえる。句読点で終え、仮歯の書き方をそろえる。"""
    text, _ = normalize_spellings((text or "").strip())
    if text and text[-1] not in "。！？":
        text += "。"
    return text
