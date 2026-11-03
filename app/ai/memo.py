"""話した内容を5つに分けて下書きにする。Claude の仕事は「分ける」と「もとの話の抜き出しを付ける」だけ。

- 各項目に付いた抜き出しが、話した文字の中に本当にあるかをプログラムで調べる。無い項目は出さない。
- 否定・取り消し・訂正があれば一番新しい言い方に従う。部位・時期・薬の名前は話した言葉のまま。
- 話していない治療、提案、診断は足さない。無い項目は空のまま。
"""
import json
import re
import unicodedata

from app.ai import fixtalk
from app.ai.fixtalk import finish_text
from app.ai.gateway import Gateway

SECTIONS = [
    ("done", "今日やったこと"),
    ("explained", "説明したこと"),
    ("next_plan", "次回の予定"),
    ("future_plan", "今後の治療計画"),
    ("future_policy", "今後の治療方針"),
]
KEYS = [k for k, _ in SECTIONS]
TITLES = dict(SECTIONS)

SYSTEM = (
    "あなたは歯科医院の記録の整理係です。歯科医師か歯科衛生士が話した内容を、次の5つに分けます。"
    "診断も治療の提案もしません。話していないことは足しません。\n"
    "done=今日やったこと / explained=患者様に説明したこと / next_plan=次回の予定 / "
    "future_plan=今後の治療計画 / future_policy=今後の治療方針\n"
    "決まり:\n"
    "- 各項目に、もとになった話の抜き出し quote を付けます。quote は話した文字からそのまま写した一続きの文字にします。言い換えません。\n"
    "- text は短くまとめた1文にします。句読点（、。）を入れて、カルテにそのまま書ける文にします。"
    "部位（右下6番など）、時期（二週間後など）、薬の名前は、話した言葉のままにします。仮歯は TeC と書き、TEK とは書きません。\n"
    "- 否定（〜はしません）、取り消し（〜はやめます）、訂正（右下と言いましたが左下です）があるときは、一番新しい言い方に従います。"
    "取り消された内容や、訂正前の言い方は text に入れません。\n"
    "- 話していない治療、提案、診断は足しません。該当する話が無い項目は空の配列にします。\n"
    "次のJSONだけを返します。説明文は付けません。\n"
    '{"done":[{"text":"…","quote":"…"}],"explained":[],"next_plan":[],"future_plan":[],"future_policy":[]}'
)


def _squash(s: str) -> str:
    """抜き出しの照合用。全角半角と空白・句読点の違いを無くす。"""
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s、。，．,.！!？?「」『』（）()・…~〜\-ー]+", "", s)


def parse_items(raw: str, transcript: str) -> dict:
    """Claude の応答から5つの項目を取り出す。形が違えば ValueError。抜き出しが話の中に無い行は捨てる。"""
    s = (raw or "").strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    if m:
        s = m.group(1)
    try:
        obj = json.loads(s)
    except ValueError:
        raise ValueError("応答の形が違います") from None
    if not isinstance(obj, dict) or set(obj) != set(KEYS):
        raise ValueError("応答の形が違います")
    spoken = _squash(transcript)
    out = {}
    for k in KEYS:
        rows = obj[k]
        if not isinstance(rows, list):
            raise ValueError("応答の形が違います")
        kept = []
        for r in rows:
            if not isinstance(r, dict) or set(r) != {"text", "quote"} or not all(isinstance(r[x], str) for x in r):
                raise ValueError("応答の形が違います")
            q = _squash(r["quote"])
            if r["text"].strip() and q and q in spoken:  # 抜き出しが無い、話の中に無い行は出さない
                kept.append({"text": finish_text(r["text"]), "quote": r["quote"].strip()})
        out[k] = kept
    return out


def organize(transcript: str, sens, gateway: Gateway) -> dict:
    """話した文字を Claude に渡して5つに分ける。送るのは送信口だけ（伏字つき）。
    sens は sensitive_from_db(con) の結果（接続は別の処理に渡さないので、呼ぶ側で作る）。"""
    reply = gateway.send(f"話した内容:\n{transcript}", sens, system=SYSTEM, max_tokens=4000, purpose="memo")
    return parse_items(reply.text, transcript)  # 名前を戻したあとの文字で、話した文字と照らす


def make_draft(transcript: str, sens, gateway: Gateway, fix: bool = True):
    """下書きを作る。先に聞き違いを直し（fix=True）、直した文字を5つに分ける。
    抜き出しの確認は直した文字に対して行う。戻り値: (項目, 直した文字, 直した一覧)。
    fix=False は、人が直した文字（そのまま5つに分ける）。"""
    if not fix:
        return organize(transcript, sens, gateway), transcript, []
    fixed, fixes = fixtalk.fix_transcript(transcript, sens, gateway)
    return organize(fixed, sens, gateway), fixed, fixes


def body_lines(items: dict) -> str:
    """drafts.body 用。1行に1項目。"""
    return "\n".join(f"{TITLES[k]}: {r['text']}" for k in KEYS for r in items.get(k, []))
