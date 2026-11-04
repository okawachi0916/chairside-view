"""下書きの誤字直し: 聞き違いを直す段、文字起こしの initial_prompt（ボタン1だけ）、書き方の統一。本物の Claude と文字起こしは呼ばない。"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from app.ai import fixtalk, memo
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from app.ai.redact import Sensitive

ROOT = Path(__file__).resolve().parents[1]
SENS = Sensitive(patients=[], staff=[], clinics=[])

# 今朝の聞き違いを作り直した2つの録音の文字（実際の文字ではない。聞き違いは院長の例のとおり）
REC1 = "今日は右下6番の根幹重点をしました。肺脳があったので洗浄しました。次回は2週間後に次第蓄造をします。"
REC2 = "右下6番の次第地駆動の形成をしました。仮歯はTEKを入れました。"
def fx(a, b, ay="あ", by="あ"):
    """Claude の直し1つ（読みつき）。読みを指定しなければ、同じ読みとして渡す。"""
    return {"from": a, "to": b, "from_yomi": ay, "to_yomi": by}


FIX1 = [fx("根幹重点", "根管充填"), fx("肺脳", "排膿"), fx("次第蓄造", "支台築造")]
FIX2 = [fx("次第地駆動", "支台築造")]


def gw(tmp_path, fix_reply="[]", reply="{}"):
    mouth = ScriptedMouth(reply, fix_reply=json.dumps(fix_reply, ensure_ascii=False))
    return Gateway(mouth=mouth, log_dir=tmp_path / "log"), mouth


# ---- 設定 ----

def test_dental_terms_config():
    cfg = json.loads((ROOT / "config" / "dental_terms.json").read_text(encoding="utf-8"))
    assert 0 < len(cfg["terms"]) <= 80  # 語は80語以内
    for need in ("覆髄", "直接覆髄", "間接覆髄", "断髄", "根管拡大", "根管洗浄", "除去", "補綴", "プロビジョナル", "抜髄"):
        assert need in cfg["terms"]
    assert len(set(cfg["terms"])) == len(cfg["terms"])
    p = fixtalk.initial_prompt()
    assert p.startswith(cfg["sentence"]) and all(t in p for t in cfg["terms"]) and len(p) < 800
    assert "TeC" in cfg["terms"] and "TEK" not in "".join(cfg["terms"])
    for need in ("根管充填", "排膿", "支台築造"):
        assert need in cfg["terms"]


def test_broken_config_gives_no_prompt(monkeypatch, tmp_path):
    bad = tmp_path / "t.json"
    bad.write_text("{壊れた", encoding="utf-8")
    monkeypatch.setattr(fixtalk, "CONFIG", bad)
    assert fixtalk.initial_prompt() == "" and fixtalk.terms() == []
    assert fixtalk.normalize_spellings("TEKを入れた")[0] == "TEKを入れた"


# ---- 聞き違いを直す段 ----

def test_fixes_apply_to_both_recordings(tmp_path):
    for talk, fixes, want in ((REC1, FIX1, ["根管充填", "排膿", "支台築造"]), (REC2, FIX2, ["支台築造", "TeC"])):
        g, mouth = gw(tmp_path, fixes)
        text, done = fixtalk.fix_transcript(talk, SENS, g)
        assert all(w in text for w in want), (text, want)
        assert not any(bad in text for bad in ("根幹重点", "肺脳", "次第蓄造", "次第地駆動", "TEK"))
        assert text.count("右下6番") == talk.count("右下6番") and "2週間後" in text or "2週間後" not in talk  # 数字は残る
        assert len(mouth.fix_sent) == 1
        system, user = mouth.fix_sent[0]
        assert "音声認識で文字にしたもので、聞き違いがあります" in system and "同じか近い読み" in system
        assert "迷う所は直しません" in system and "言い換えません" in system and "言葉を足しません" in system
        assert talk in user
    # 直した一覧は「元→直し」で残る（書き方の統一・決まりで直したものもここに入る。決まりにある言葉は決まりが直す）
    _, done = fixtalk.fix_transcript(REC2, SENS, gw(tmp_path, FIX2)[0])
    assert {"from": "次第地駆動", "to": "支台築造", "by": "rule"} in done and {"from": "TEK", "to": "TeC", "by": "rule"} in done


def test_only_words_in_the_text_are_accepted():
    raw = json.dumps([fx("そんな言葉は無い", "根管充填"), fx("肺脳", "排膿")], ensure_ascii=False)
    assert [f["from"] for f in fixtalk.parse_fixes(raw, REC1)] == ["肺脳"]  # 話の文字に無い from は捨てる


@pytest.mark.parametrize("a,b", [
    ("右下6番", "右下7番"),            # 部位の番号
    ("2週間後", "3週間後"),            # 数字
    ("2週間後", "週間後"),             # 数字を消す
    ("10月23日", "10月24日"),          # 日付
    ("アモキシシリン250mg", "アモキシシリン500mg"),  # 薬の量
    ("二週間後", "三週間後"),          # 漢数字
    ("肺脳", "排膿をして抗菌薬を処方するのがよいです"),   # 言葉を足す・長過ぎる
    ("肺脳", "排膿。"),                 # 文を作る
    ("肺", "排"),                       # 1字の置き換え
    ("肺脳", "肺脳"),                   # 同じ
])
def test_unsafe_fixes_are_rejected(a, b):
    talk = "右下6番を2週間後に、10月23日にアモキシシリン250mgで、二週間後、肺脳"
    assert fixtalk.parse_fixes(json.dumps([fx(a, b)], ensure_ascii=False), talk) == []


def test_numbers_never_change_even_if_claude_tries(tmp_path):
    talk = "右下6番の根幹重点を2週間後にします。10月23日のアモキシシリン250mgを続けます。"
    bad = [fx("右下6番", "左下7番"), fx("2週間後", "1週間後"), fx("250mg", "500mg"),
           fx("10月23日", "10月30日"), fx("根幹重点", "根管充填")]
    text, _ = fixtalk.fix_transcript(talk, SENS, gw(tmp_path, bad)[0])
    assert text == talk.replace("根幹重点", "根管充填")


@pytest.mark.parametrize("raw", ["", "直しは無し", "{}", '{"from":"肺脳","to":"排膿","from_yomi":"はいのう","to_yomi":"はいのう"}',
                                 "[1]", "null"])
def test_bad_shape_is_an_error(raw):
    with pytest.raises(ValueError):
        fixtalk.parse_fixes(raw, REC1)


def test_fenced_json_and_empty_list_are_ok():
    assert fixtalk.parse_fixes('```json\n[{"from":"肺脳","to":"排膿","from_yomi":"はいのう","to_yomi":"はいのう"}]\n```', REC1)[0]["to"] == "排膿"
    assert fixtalk.parse_fixes("[]", REC1) == []


def test_unsure_means_no_change(tmp_path):
    plain = "今日は右下6番の形成をしました。次回は2週間後に印象をとります。"
    text, done = fixtalk.fix_transcript(plain, SENS, gw(tmp_path, [])[0])
    assert text == plain and done == []


def test_known_mishearings_are_fixed_by_rule_even_if_claude_misses_them(tmp_path):
    """G19b: Claude が直さなかった根幹重点・肺脳・次第蓄造・次第地駆動も、決まり（spellings）で直る。"""
    text, done = fixtalk.fix_transcript(REC1, SENS, gw(tmp_path, [])[0])
    assert text == "今日は右下6番の根管充填をしました。排膿があったので洗浄しました。次回は2週間後に支台築造をします。"
    assert {d["by"] for d in done} == {"rule"}
    text2, _ = fixtalk.fix_transcript("右下6番の次第地駆動の形成をしました。", SENS, gw(tmp_path, [])[0])
    assert text2 == "右下6番の支台築造の形成をしました。"


# ---- 書き方の統一（仮歯は TeC） ----

@pytest.mark.parametrize("before,after", [
    ("仮歯はTEKを入れた", "仮歯はTeCを入れた"), ("ＴＥＫを外した", "TeCを外した"), ("テックを入れた", "TeCを入れた"),
    ("tekで様子を見る", "TeCで様子を見る"), ("TEKとテックを", "TeCとTeCを"),
])
def test_tec_spelling(before, after):
    assert fixtalk.normalize_spellings(before)[0] == after


@pytest.mark.parametrize("keep", ["テックスという言葉", "ATEKA", "TEKS", "ハイテック製"])
def test_tec_spelling_does_not_touch_other_words(keep):
    assert fixtalk.normalize_spellings(keep)[0] == keep


def test_finish_text_gives_punctuation_and_tec():
    assert fixtalk.finish_text("仮歯のTEKを入れる") == "仮歯のTeCを入れる。"
    assert fixtalk.finish_text("根管充填をした。") == "根管充填をした。"
    assert fixtalk.finish_text("  ") == ""


def test_organize_prompt_asks_for_punctuation_and_tec():
    assert "句読点" in memo.SYSTEM and "TeC" in memo.SYSTEM and "TEK とは書きません" in memo.SYSTEM


# ---- 5つに分ける（直した文に対して、話していないことは足さない）----

def reply_for(text_done, quote):
    return json.dumps({**{k: [] for k in memo.KEYS}, "done": [{"text": text_done, "quote": quote}]}, ensure_ascii=False)


def test_items_are_made_from_fixed_text_and_quotes_checked_against_it(tmp_path):
    ok = reply_for("右下6番の根管充填", "右下6番の根管充填をしました")
    items, fixed, fixes = memo.make_draft("今日は右下6番の根幹重点をしました。", SENS, gw(tmp_path, FIX1[:1], ok)[0])
    assert fixed == "今日は右下6番の根管充填をしました。" and fixes[0]["to"] == "根管充填"
    assert items["done"] == [{"text": "右下6番の根管充填。", "quote": "右下6番の根管充填をしました"}]
    # 聞き違いのままの抜き出しは、直した文には無いので捨てる
    old = reply_for("右下6番の根管充填", "右下6番の根幹重点をしました")
    items, _, _ = memo.make_draft("今日は右下6番の根幹重点をしました。", SENS, gw(tmp_path, FIX1[:1], old)[0])
    assert items["done"] == []


def test_untalked_treatment_is_not_added(tmp_path):
    talk = "今日は右下6番の根幹重点をしました。"
    made_up = json.dumps({**{k: [] for k in memo.KEYS},
                          "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"},
                                   {"text": "抜歯をした", "quote": "抜歯をしました"}]}, ensure_ascii=False)
    items, _, _ = memo.make_draft(talk, SENS, gw(tmp_path, FIX1[:1], made_up)[0])
    assert [r["text"] for r in items["done"]] == ["右下6番の根管充填。"] and "抜歯" not in memo.body_lines(items)
    # 直しの一覧で話していない治療を足そうとしても、from が話に無いので入らない
    sneaky = [fx("抜歯をしました", "抜歯と投薬をしました")]
    text, _ = fixtalk.fix_transcript(talk, SENS, gw(tmp_path, sneaky)[0])
    assert text == fixtalk.normalize_spellings(talk)[0]  # 決まりの直し（根幹重点→根管充填）以外は変わらない


def test_human_fixed_text_is_not_auto_fixed(tmp_path):
    g, mouth = gw(tmp_path, FIX1, reply_for("右下6番の根幹重点", "右下6番の根幹重点をしました"))
    items, fixed, fixes = memo.make_draft("今日は右下6番の根幹重点をしました。", SENS, g, fix=False)
    assert fixes == [] and fixed.startswith("今日は右下6番の根幹重点") and mouth.fix_sent == []


# ---- 文字起こし: ボタン1だけ initial_prompt ----

class FakeWhisper:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **kw):
        self.calls.append(kw)

        class Seg:
            text = "右下6番を2週間後に"

        return [Seg()], None


def test_initial_prompt_only_for_button1(monkeypatch):
    from app.ai import recpipe
    from app.voice import transcribe as tr

    fw = FakeWhisper()
    monkeypatch.setattr(tr, "_model", lambda name: fw)
    monkeypatch.setattr(tr, "to_pcm", lambda data: b"pcm")
    monkeypatch.setattr(recpipe.fake, "fake_transcript", lambda: None)
    # ボタン1（録音）: 歯科の短い一文と主な語を渡す
    assert recpipe._transcribe(Path(__file__)) == "右下6番を2週間後に"
    assert fw.calls[-1]["initial_prompt"] == fixtalk.initial_prompt() and "根管充填" in fw.calls[-1]["initial_prompt"]
    # ボタン2（声の指示 /voice/transcribe）: 渡さない
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).post("/voice/transcribe", content=b"x")
    assert r.status_code == 200 and r.json()["text"] == "右下6番を2週間後に"
    assert "initial_prompt" not in fw.calls[-1]
    # 数字は文字起こしの結果からも落ちない（渡し方で結果の文字を変えていない）
    assert "6" in r.json()["text"] and "2" in r.json()["text"]


# ---- 本物の文字起こしで、数字が落ちないことを確かめる（GPU。声の窓だけが動かす）----

@pytest.mark.gpu
def test_numbers_survive_initial_prompt_with_real_whisper(tmp_path):
    from app.voice import transcribe as tr

    raw = tmp_path / "raw.wav"
    phrase = "右下6番の根管充填を2週間後に行います。"
    script = ("Add-Type -AssemblyName System.Speech;$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
              "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ja-JP' } | Select-Object -First 1;"
              "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
              f"$s.SetOutputToWaveFile('{raw}');$s.Speak('{phrase}');$s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    with wave.open(str(raw), "rb") as r:
        assert r.getnframes() > 0
    pcm = tr.to_pcm(raw.read_bytes())
    with_prompt = tr.transcribe(pcm, initial_prompt=fixtalk.initial_prompt())["text"]
    without = tr.transcribe(pcm)["text"]
    digits = lambda s: [c for c in s if c in "0123456789０１２３４５６７８９"]  # noqa: E731
    assert len(digits(with_prompt)) >= len(digits(without)) > 0, (with_prompt, without)


# ---- G19d: 読みが違う言葉には替えない ----

def _reading_fix(a, b, ay, by):
    return json.dumps([{"from": a, "to": b, "from_yomi": ay, "to_yomi": by}], ensure_ascii=False)


def test_g19d_fuku_zui_becomes_fukuzui_not_batsuzui(tmp_path):
    """「副髄」は覆髄になる。Claude が抜髄と返しても（読みが違う）捨てる。抜髄は抜髄のまま。"""
    talk = "右下の5番は除去と副髄をします。"
    wrong = _reading_fix("副髄", "抜髄", "ふくずい", "ばつずい")
    text, done = fixtalk.fix_transcript(talk, SENS, gw(tmp_path, json.loads(wrong))[0])
    assert text == "右下の5番は除去と覆髄をします。" and "抜髄" not in text
    assert done == [{"from": "副髄", "to": "覆髄", "by": "rule"}]  # 決まりで直したものも一覧に出る
    keep = "右下の5番は抜髄をします。"
    assert fixtalk.fix_transcript(keep, SENS, gw(tmp_path, [])[0])[0] == keep


def test_g19d_different_reading_is_dropped_by_the_program():
    talk = "右下6番は副髄をします。"
    assert fixtalk.parse_fixes(_reading_fix("副髄", "抜髄", "ふくずい", "ばつずい"), talk) == []
    assert fixtalk.parse_fixes(_reading_fix("副髄", "覆髄", "ふくずい", "ふくずい"), talk)[0]["to"] == "覆髄"
    # 1字だけ違う（濁点・長音・小さい字）は使う
    assert fixtalk.parse_fixes(_reading_fix("副髄", "覆髄", "ふくずい", "ふくすい"), talk)
    assert fixtalk.parse_fixes(_reading_fix("副髄", "覆髄", "ふくずい", "フクズイ"), talk)
    assert fixtalk.parse_fixes(_reading_fix("副髄", "覆髄", "きょう", "きよう"), talk)
    # 2字以上違う、ひらがなでない読みは捨てる
    assert fixtalk.parse_fixes(_reading_fix("副髄", "覆髄", "ふくずい", "ふくずいい"), talk)  # 1字足りないだけは使う
    assert fixtalk.parse_fixes(_reading_fix("副髄", "覆髄", "ふくずい", "ふくすいい"), talk) == []
    assert fixtalk.parse_fixes(_reading_fix("副髄", "覆髄", "ふくずい", "覆髄"), talk) == []


def test_g19d_missing_or_broken_reading_drops_only_that_fix():
    talk = "根幹重点をして肺脳があった。"
    rows = [{"from": "根幹重点", "to": "根管充填"},                                     # 読みが無い
            {"from": "肺脳", "to": "排膿", "from_yomi": "はいのう", "to_yomi": 5},       # 読みの型が違う
            {"from": "肺脳", "to": "排膿", "from_yomi": "はいのう", "to_yomi": "はいのう"}]
    got = fixtalk.parse_fixes(json.dumps(rows, ensure_ascii=False), talk)
    assert [f["from"] for f in got] == ["肺脳"]


def test_g19d_four_common_mishearings_are_fixed_by_rules_without_claude(tmp_path):
    talk = "根幹重点をして、肺脳があった。次第蓄造と次第地駆動。副髄もした。"
    text, done = fixtalk.fix_transcript(talk, SENS, gw(tmp_path, [])[0])
    assert text == "根管充填をして、排膿があった。支台築造と支台築造。覆髄もした。"
    assert {d["from"] for d in done} == {"根幹重点", "肺脳", "次第蓄造", "次第地駆動", "副髄"} and all(d["by"] == "rule" for d in done)


def test_g19d_prompt_says_same_reading_and_has_the_example():
    s = fixtalk.SYSTEM
    assert "同じ読みの言葉にします。読みが違う言葉には替えません。同じ読みの言葉が見つからなければ直しません" in s
    assert "副髄→覆髄（抜髄ではない。読みが違う）" in s and "from_yomi" in s and "to_yomi" in s


def test_g19d_same_items_are_merged_into_one():
    talk = "今日は右下6番の根管充填をしました。今日は右下6番の根管充填をしました。"
    row = {"text": "右下6番の根管充填。", "quote": "右下6番の根管充填をしました"}
    raw = json.dumps({**{k: [] for k in memo.KEYS}, "done": [row, dict(row)]}, ensure_ascii=False)
    assert len(memo.parse_items(raw, talk)["done"]) == 1
