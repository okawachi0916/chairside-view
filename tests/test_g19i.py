"""G19i（と G19k）: 院長の録音（台本1・花子様）の文字で、6つの聞き違いが全部直る。偽物の口。"""
from app.ai import fixtalk
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from app.ai.redact import Sensitive
from tests.polish_helper import polish_reply
from tests.test_fixtalk import REC1

SENS = Sensitive(patients=[], staff=[], clinics=[])
# 院長が11/4 23:11に台本1を読んだ録音の、話したままの文字（rec_4.webm の文字起こしの結果）
TALK = ("右下6番の根管充填を行いました。前回あった肺のが止まっています。X線では根尖病変は小さくなってきています。"
        "次回は次第畜造をして肩を取ります。左上の5番は陰霊を外したところ、カリエスが深かったので副髄をして、仮の詰め物をしています。"
        "全身既往は高血圧があり、服薬は高圧剤を1種類飲まれています。")
FIXED = ("右下6番の根管充填を行いました。前回あった排膿が止まっています。X線では根尖病変は小さくなってきています。"
         "次回は支台築造をして型を取ります。左上の5番はインレーを外したところ、カリエスが深かったので覆髄をして、仮の詰め物をしています。"
         "全身既往は高血圧があり、服薬は降圧剤を1種類飲まれています。")
PAIRS = [("肺の", "排膿"), ("次第畜造", "支台築造"), ("肩を取", "型を取"), ("高圧剤", "降圧剤"), ("副髄", "覆髄"), ("陰霊", "インレー")]


def run(tmp_path, talk=TALK, pairs=PAIRS):
    return fixtalk.polish(talk, SENS, Gateway(mouth=ScriptedMouth("{}", polish_reply=polish_reply(talk, pairs)), log_dir=tmp_path / "log"))


def test_six_mishearings_are_fixed_in_the_doctors_recording(tmp_path):
    res = run(tmp_path)
    assert res["text"] == FIXED
    for w in ("肩を取", "高圧剤", "肺の", "次第畜造", "副髄", "陰霊"):
        assert w not in res["text"]
    # 「直した聞き違い（元 → 直し）」の欄には6つ並ぶ
    assert {(d["from"], d["to"]) for d in res["fixes"]} == set(PAIRS)


def test_mishearings_stay_in_the_transcript_and_polish_is_the_screen_text(tmp_path):
    """聞き取りのままの文は消さない（呼ぶ側が保存する）。画面に出すのは清書。"""
    res = run(tmp_path)
    assert res["text"] != TALK and "肩を取ります" in TALK and "型を取ります" in res["text"]


def test_other_recordings_are_fixed_as_before(tmp_path):
    pairs = [("根幹重点", "根管充填"), ("肺脳", "排膿"), ("次第蓄造", "支台築造")]
    res = run(tmp_path, REC1, pairs)
    assert res["text"] == "今日は右下6番の根管充填をしました。排膿があったので洗浄しました。次回は2週間後に支台築造をします。"


def test_fixes_missing_from_claudes_list_are_still_listed(tmp_path):
    """Claude が全文では6か所直したのに、一覧には2つしか書かなかったとき（実際にあった）も、一覧は6つ並ぶ。"""
    reply = polish_reply(TALK, PAIRS[:2], text=FIXED)
    res = fixtalk.polish(TALK, SENS, Gateway(mouth=ScriptedMouth("{}", polish_reply=reply), log_dir=tmp_path / "log"))
    assert res["text"] == FIXED and len(res["fixes"]) == 6
    shown = {f["to"] for f in res["fixes"]}
    for w in ("排膿", "支台築造", "降圧剤", "覆髄", "インレー"):
        assert w in shown
    assert any(f["to"].endswith("型") or "型" in f["to"] for f in res["fixes"])
    assert all(f["to"] in res["text"] and f["from"] in TALK for f in res["fixes"])
