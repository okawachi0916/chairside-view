"""G19i: 院長の録音（台本1・花子様）の文字で、6つの聞き違いが全部直る。「肩を取」「高圧剤」の決まりを足した。偽物の口。"""
import json
from pathlib import Path

from app.ai import fixtalk
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from app.ai.redact import Sensitive
from tests.test_fixtalk import fx

ROOT = Path(__file__).resolve().parents[1]
SENS = Sensitive(patients=[], staff=[], clinics=[])
# 院長が11/4 23:11に台本1を読んだ録音の、話したままの文字（rec_4.webm の文字起こしの結果）
TALK = ("右下6番の根管充填を行いました。前回あった肺のが止まっています。X線では根尖病変は小さくなってきています。"
        "次回は次第畜造をして肩を取ります。左上の5番は陰霊を外したところ、カリエスが深かったので副髄をして、仮の詰め物をしています。"
        "全身既往は高血圧があり、服薬は高圧剤を1種類飲まれています。")
FIXED = ("右下6番の根管充填を行いました。前回あった排膿が止まっています。X線では根尖病変は小さくなってきています。"
         "次回は支台築造をして型を取ります。左上の5番はインレーを外したところ、カリエスが深かったので覆髄をして、仮の詰め物をしています。"
         "全身既往は高血圧があり、服薬は降圧剤を1種類飲まれています。")
# 本物の Claude は「肺の→排膿」「次第畜造→支台築造」の2つを直した（あとの4つは決まり）
CLAUDE_FIX = [fx("肺の", "排膿", "はいのう", "はいのう"), fx("次第畜造", "支台築造", "しだいちくぞう", "しだいちくぞう")]


def run(tmp_path, claude=CLAUDE_FIX, talk=TALK):
    mouth = ScriptedMouth("{}", fix_reply=json.dumps(claude, ensure_ascii=False))
    return fixtalk.fix_transcript(talk, SENS, Gateway(mouth=mouth, log_dir=tmp_path / "log"))


def test_six_mishearings_are_fixed_in_the_doctors_recording(tmp_path):
    text, done = run(tmp_path)
    assert text == FIXED
    for w in ("肩を取", "高圧剤", "肺の", "次第畜造", "副髄", "陰霊"):
        assert w not in text
    assert [(d["from"], d["to"]) for d in done if d["by"] == "claude"] == [("肺の", "排膿"), ("次第畜造", "支台築造")]
    # 「直した聞き違い（元 → 直し）」の欄には6つ並ぶ
    assert {(d["from"], d["to"]) for d in done} == {
        ("肺の", "排膿"), ("次第畜造", "支台築造"), ("肩を取", "型を取"), ("高圧剤", "降圧剤"), ("副髄", "覆髄"), ("陰霊", "インレー")}


def test_the_two_new_rules_work_without_claude(tmp_path):
    text, _ = run(tmp_path, claude=[], talk="次回は型を取ります。肩を取ります。降圧剤と高圧剤と高圧材を飲まれています。")
    assert text == "次回は型を取ります。型を取ります。降圧剤と降圧剤と降圧剤を飲まれています。"


def test_correct_words_and_other_shoulder_words_are_left_alone(tmp_path):
    ok = "型を取りました。降圧剤を飲まれています。肩こりがあり、肩を痛めたそうです。"
    assert run(tmp_path, claude=[], talk=ok)[0] == ok


def test_terms_added_and_other_recordings_unchanged(tmp_path):
    cfg = json.loads((ROOT / "config" / "dental_terms.json").read_text(encoding="utf-8"))
    assert "降圧剤" in cfg["terms"] and "型取り" in cfg["terms"] and len(cfg["terms"]) <= 80
    assert "肩を取" in cfg["readings"]["型を取"] and {"高圧剤", "高圧材"} <= set(cfg["readings"]["降圧剤"])
    from tests.test_fixtalk import FIX1, REC1
    text, _ = run(tmp_path, claude=FIX1, talk=REC1)  # 今までの録音の直しは変わらない
    assert text == "今日は右下6番の根管充填をしました。排膿があったので洗浄しました。次回は2週間後に支台築造をします。"
