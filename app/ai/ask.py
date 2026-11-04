"""自由な質問に答える。Claude は記録の番号を選ぶだけ。画面に出す本文はデータベースの文字をそのまま使う。

- 「質問」に分けられた言葉だけを Claude へ送る（無関係・聞き取り失敗・操作は送らない）。
- 送るのは app/ai/gateway.py の送信口だけ。
- 応答の形と番号をここで調べる。渡していない番号、形の違う応答は捨てて「もう一度お願いします」。
"""
import json
import re

from app.ai.gateway import Gateway, sensitive_from_db
from app.ai.quick import pick_entry, pick_record
from app.ai.records import build_records
from app.ai.redact import RedactionFailed
from app.ai.settings import ClaudeUnavailable
from app.voice.interpret import QUESTION, interpret

MSG_RETRY = "もう一度お願いします"
MSG_NONE = "記録がありません"
MSG_UNAVAILABLE = "質問の機能は使えません"
MSG_STOPPED = "送信を止めました（伏字に失敗しました）"

SYSTEM = (
    "あなたは歯科医院の記録の検索係です。下の番号付きの記録から、質問に答えが書いてある記録を1つ選びます。"
    "診断も治療の提案もしません。文章で答えず、次のJSONだけを返します。\n"
    '{"result":"found","record":記録の番号} … 答えが書いてある記録がある\n'
    '{"result":"none"} … 記録に答えが無い\n'
    '{"result":"unclear"} … 質問の意味が分からず、聞き直しが要る\n'
    "これからの予定を聞かれたら「治療計画」の記録を選び、過去にしたことを聞かれたら「診療メモ」や「治療歴」の記録を選びます。"
    "番号は渡した記録の番号だけを使います。記録に無いことを推測で見つかったことにしません。"
)


def build_prompt(records, question: str) -> str:
    body = "\n".join(f"記録{r.number}: {r.prompt}" for r in records)
    return f"この患者様の記録:\n{body}\n\n質問: {question}"


def parse_reply(raw: str, numbers):
    """('found', 番号) / ('none',) / ('unclear',) / None（形が違う）。"""
    s = (raw or "").strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    if m:
        s = m.group(1)
    try:
        obj = json.loads(s)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    res = obj.get("result")
    if res == "found" and set(obj) == {"result", "record"}:
        n = obj["record"]
        if isinstance(n, int) and not isinstance(n, bool) and n in numbers:
            return ("found", n)
        return None
    if res in ("none", "unclear") and set(obj) == {"result"}:
        return (res,)
    return None


def found(rec, sends: int) -> dict:
    return {"result": "found", "title": rec.kind, "lines": rec.lines, "source": rec.source,
            "part": rec.part, "ref": rec.ref, "sends": sends}


def answer(text: str, con, patient_id: int, gateway: Gateway, quick: bool = True,
           visit_date: str | None = None) -> dict:
    """戻り値の sends は Claude へ送った回数。quick=False は、表を使わず必ず Claude に聞く（確認用）。"""
    heard = interpret(text, "unit")
    if heard["kind"] != QUESTION:
        return {"result": "skip", "kind": heard["kind"], "message": MSG_RETRY, "sends": 0}
    records = build_records(con, patient_id)
    if quick:
        entry = pick_entry(text)  # よく聞く質問は、記録から直接出す（Claude へ送らない）
        if entry:
            rec = pick_record(entry, records, visit_date)
            if rec:
                return found(rec, 0)
            # 記録が空でも、何も出ないことが無いようにする（アレルギー・薬は「なし」と書くよう促す）。
            # ただし、ほかの記録の中にその言葉が出てくるときは、決めつけずに Claude に聞く
            whole = "".join(r.prompt for r in records)
            if entry.get("empty") and not any(t in whole for t in entry["triggers"]):
                return {"result": "none", "message": entry["empty"], "sends": 0}
    if not records:
        return {"result": "none", "message": MSG_NONE, "sends": 0}
    sens = sensitive_from_db(con)
    try:
        reply = gateway.send(build_prompt(records, text), sens, system=SYSTEM, max_tokens=1500, purpose="question")
    except ClaudeUnavailable:
        return {"result": "unavailable", "message": MSG_UNAVAILABLE, "sends": 0}
    except RedactionFailed:
        return {"result": "stopped", "message": MSG_STOPPED, "sends": 0}
    except Exception:  # noqa: BLE001  通信などの失敗。中身は画面に出さない
        return {"result": "retry", "message": MSG_RETRY, "sends": 1}
    parsed = parse_reply(reply.masked_text, {r.number for r in records})
    if parsed is None or parsed[0] == "unclear":
        return {"result": "retry", "message": MSG_RETRY, "sends": 1}
    if parsed[0] == "none":
        return {"result": "none", "message": MSG_NONE, "sends": 1}
    rec = next(r for r in records if r.number == parsed[1])
    return found(rec, 1)
