"""清書の偽物の応答を作る道具。Claude が返す JSON {"text", "fixes", "doubts"} を、直す対を指定して作る。"""
import json


def polish_reply(talk: str, pairs=(), doubts=(), text=None) -> str:
    """talk の中の「元」を「直し」に置き換えた全文を、Claude の応答（JSON）にする。text を渡せば、その文を全文として返す。"""
    out = talk
    for a, b in pairs:
        out = out.replace(a, b)
    return json.dumps({"text": text if text is not None else out,
                       "fixes": [{"from": a, "to": b} for a, b in pairs], "doubts": list(doubts)}, ensure_ascii=False)


def fixer(pairs):
    """聞き取りの文に出てくる分だけ直す応答を作る関数（ScriptedMouth の polish_reply に渡す）。"""
    return lambda talk: polish_reply(talk, [(a, b) for a, b in pairs if a in talk])


MISHEAR = [("根幹重点", "根管充填"), ("肺脳", "排膿"), ("次第蓄造", "支台築造"), ("次第地駆動", "支台築造")]
