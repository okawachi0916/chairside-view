"""聞き取りの後の清書（fixtalk.polish）: 聞き違いを文脈から直した全文を使う、安全策は2つだけ（数字・長さ）、失敗しても止めない、
書き方の統一、文字起こしのヒント（ボタン1だけ）。偽物の Claude の口。結果（直った文）を見る。"""
import json
import subprocess
import wave
from pathlib import Path

import pytest

from app.ai import fixtalk, memo
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from app.ai.redact import Sensitive
from tests.polish_helper import polish_reply

ROOT = Path(__file__).resolve().parents[1]
SENS = Sensitive(patients=[], staff=[], clinics=[])

# 今朝の聞き違いを作り直した2つの録音の文字（実際の文字ではない。聞き違いは院長の例のとおり）
REC1 = "今日は右下6番の根幹重点をしました。肺脳があったので洗浄しました。次回は2週間後に次第蓄造をします。"
REC2 = "右下6番の次第地駆動の形成をしました。仮歯はTEKを入れました。"
# G19h: 院長が11/4夜に動画用に録音した、上顎の顎補綴の話の文字起こしの結果（架空。見本 和子 様）
KAGAKU = ("この方は、上顎は顎骨鉄の疑似が入っていて、4番から7番までは上顎道まで交通した血損があります。"
          "インプラントを上顎道に近いところに打っており、そこに引っ掛ける形で顎骨鉄、疑似を入れております。"
          "お鉄を入れて、疑似を入れて、しゃべる場合は大丈夫なんですが、そうじゃないときには空気が抜ける感じでしゃべることがなかなかできません。"
          "疑似を入れても、そこで噛むことながらが難しいので、反対側で噛んでもらうようになっております。"
          "今のところ、封鎖も良好で、飲み込みも問題ありません。今後も経過観察をしていきます。")
FIX1 = [("根幹重点", "根管充填"), ("肺脳", "排膿"), ("次第蓄造", "支台築造")]
FIX2 = [("次第地駆動", "支台築造"), ("TEK", "TeC")]


def gw(tmp_path, reply=None):
    mouth = ScriptedMouth("{}", polish_reply=reply)
    return Gateway(mouth=mouth, log_dir=tmp_path / "log"), mouth


# ---- 設定 ----

def test_dental_terms_config():
    cfg = json.loads((ROOT / "config" / "dental_terms.json").read_text(encoding="utf-8"))
    assert 40 <= len(cfg["terms"]) <= 80  # 文字起こしのヒントは40〜80語
    assert len(set(cfg["terms"])) == len(cfg["terms"])
    p = fixtalk.initial_prompt()
    assert p.startswith(cfg["sentence"]) and all(t in p for t in cfg["terms"]) and len(p) < 800
    assert "TeC" in cfg["terms"] and "TEK" not in "".join(cfg["terms"])
    for need in ("根管充填", "排膿", "支台築造", "補綴", "義歯"):
        assert need in cfg["terms"]
    # 清書に渡す一覧は、terms と合わせて、重なりなし
    g = fixtalk.glossary()
    assert len(set(g)) == len(g) and set(cfg["terms"]) <= set(g) and len(g) > 250
    for need in ("生活歯", "失活歯", "根尖性歯周炎", "ガッタパーチャ", "二次う蝕", "フラップ手術", "サイナスリフト", "ワーファリン", "歯式"):
        assert need in g


def test_broken_config_gives_no_prompt(monkeypatch, tmp_path):
    bad = tmp_path / "t.json"
    bad.write_text("{壊れた", encoding="utf-8")
    monkeypatch.setattr(fixtalk, "CONFIG", bad)
    assert fixtalk.initial_prompt() == "" and fixtalk.terms() == [] and fixtalk.glossary() == []
    assert fixtalk.normalize_spellings("TEKを入れた")[0] == "TEKを入れた"


# ---- 清書: 文脈から直した全文が本文になる ----

def test_polished_text_is_used_and_fixes_are_listed(tmp_path):
    g, mouth = gw(tmp_path, polish_reply(REC1, FIX1))
    res = fixtalk.polish(REC1, SENS, g, "今日の予約の処置: 根管治療 右下6番")
    assert res["text"] == "今日は右下6番の根管充填をしました。排膿があったので洗浄しました。次回は2週間後に支台築造をします。"
    assert res["polished"] and res["note"] == ""
    assert [(f["from"], f["to"]) for f in res["fixes"]] == FIX1 and all(f["by"] == "claude" for f in res["fixes"])
    system, user = mouth.polish_sent[0]
    assert user == fixtalk.USER_PREFIX + REC1
    # Claude へ渡すもの: 歯科の診療の話であること、患者様の情報、歯科の言葉の一覧、聞き違いの例
    assert "歯科の診療に関わる話だけをしています" in system and "今日の予約の処置: 根管治療 右下6番" in system
    assert "生活歯" in system and "ガッタパーチャ" in system and "根幹重点→根管充填" in system
    assert "読みが違う言葉でも、話の流れから明らかなら直してよい" in system and "迷う言葉は直さずに" in system


def test_reading_does_not_matter_if_the_flow_makes_it_clear(tmp_path):
    """読みが違う直し（生活死→生活歯 など）も、Claude の清書なら使う。プログラムは読みを比べない。"""
    talk = "左下3番にレントゲンで根尖病変を認めます。なので、こちらは生活死ではなく既に失活しているということです。"
    res = fixtalk.polish(talk, SENS, gw(tmp_path, polish_reply(talk, [("生活死", "生活歯")]))[0])
    assert res["text"].endswith("こちらは生活歯ではなく既に失活しているということです。") and res["polished"]
    assert res["fixes"] == [{"from": "生活死", "to": "生活歯", "by": "claude"}]
    # 画面の本文は清書。直した言葉に下線が付く
    assert '<u class="pf-fix">生活歯</u>' in fixtalk.marked_html(res["text"], res["fixes"], res["doubts"])


def test_kagaku_talk_is_fixed_by_context(tmp_path):
    pairs = [("顎骨鉄", "顎補綴"), ("疑似", "義歯"), ("上顎道", "上顎洞"), ("血損", "欠損"), ("お鉄を入れ", "補綴を入れ")]
    res = fixtalk.polish(KAGAKU, SENS, gw(tmp_path, polish_reply(KAGAKU, pairs))[0])
    for w in ("顎補綴", "義歯", "上顎洞", "欠損", "補綴を入れて"):
        assert w in res["text"]
    for w in ("顎骨鉄", "疑似", "上顎道", "血損", "お鉄"):
        assert w not in res["text"]


def test_correct_text_stays_the_same(tmp_path):
    ok = "右下6番の根管充填をしました。降圧剤を飲まれています。生活歯です。"
    res = fixtalk.polish(ok, SENS, gw(tmp_path)[0])  # 偽物の既定: 聞き取りの文をそのまま返す
    assert res["text"] == ok and res["fixes"] == [] and res["doubts"] == [] and res["polished"] and res["note"] == ""


def test_doubts_are_marked_and_left_in_the_text(tmp_path):
    talk = "左下6番はキョウザンをしました。"
    res = fixtalk.polish(talk, SENS, gw(tmp_path, polish_reply(talk, [], doubts=["キョウザン", "本文に無い言葉"]))[0])
    assert res["text"] == talk and res["doubts"] == ["キョウザン"]
    assert '<mark class="pf-doubt">キョウザン</mark>' in fixtalk.marked_html(res["text"], res["fixes"], res["doubts"])


def test_marked_html_escapes_and_underlines_every_place():
    h = fixtalk.marked_html("<b>排膿</b>と排膿", [{"from": "肺脳", "to": "排膿"}], [])
    assert h == '&lt;b&gt;<u class="pf-fix">排膿</u>&lt;/b&gt;と<u class="pf-fix">排膿</u>'


# ---- 安全策は2つだけ ----

@pytest.mark.parametrize("changed", ["右下7番の根管充填を2週間後にします。", "右下6番の根管充填を3週間後にします。",
                                      "右下6番の根管充填を週間後にします。", "右下6番の根管充填を二週間後にします。"])
def test_changed_numbers_fall_back_to_the_transcript(tmp_path, changed):
    talk = "右下6番の根管充填を2週間後にします。"
    res = fixtalk.polish(talk, SENS, gw(tmp_path, polish_reply(talk, [], text=changed))[0])
    assert res["text"] == talk and not res["polished"] and res["note"] == fixtalk.NOTE_DIGITS


def test_text_that_grew_too_long_falls_back(tmp_path):
    talk = "右下6番の根管充填をしました。"
    long = talk + "抗菌薬を処方して、次回は2週間後に来院していただきます。"
    res = fixtalk.polish(talk, SENS, gw(tmp_path, polish_reply(talk, [], text=talk.replace("6", "６") + "痛みはありません。"))[0])
    assert res["polished"] is False and res["note"] == fixtalk.NOTE_LONG and res["text"] == talk
    res = fixtalk.polish(talk, SENS, gw(tmp_path, polish_reply(talk, [], text=long))[0])
    assert res["text"] == talk  # 2回は数字が変わる・長いのどちらでも聞き取りのまま
    # 1.3倍までは使う
    ok = "右下6番の根管充填をいたしました。"
    assert fixtalk.polish(talk, SENS, gw(tmp_path, polish_reply(talk, [], text=ok))[0])["text"] == ok


def test_no_other_narrow_rules_remain(tmp_path):
    """読みを比べる、from は20字以内、言葉を足すと見える直しを捨てる、などの狭い決まりは無い。"""
    assert not hasattr(fixtalk, "same_reading") and not hasattr(fixtalk, "parse_fixes") and not hasattr(fixtalk, "apply_fixes")
    talk = "右下6番はこうさんかいりょうをしました。"
    reply = polish_reply(talk, [("こうさんかいりょう", "酸化物の改良")])
    assert fixtalk.polish(talk, SENS, gw(tmp_path, reply)[0])["fixes"][0]["to"] == "酸化物の改良"


@pytest.mark.parametrize("raw", ["", "直しは無し", "{}", '{"text": ""}', "[1]", "null", '{"text": 5}'])
def test_failed_or_broken_polish_goes_on_with_the_transcript(tmp_path, raw):
    res = fixtalk.polish(REC1, SENS, gw(tmp_path, raw)[0])
    assert res["text"] == fixtalk.normalize_spellings(REC1)[0] == REC1 and not res["polished"] and res["note"] == fixtalk.NOTE_FAILED


def test_send_error_does_not_stop_the_flow(tmp_path):
    class Dead:
        wants_purpose = True

        def complete(self, *a, **k):
            raise RuntimeError("つながらない")

    res = fixtalk.polish(REC2, SENS, Gateway(mouth=Dead(), log_dir=tmp_path / "log"))
    assert res["text"] == "右下6番の次第地駆動の形成をしました。仮歯はTeCを入れました。" and res["note"] == fixtalk.NOTE_FAILED


def test_fenced_json_is_ok(tmp_path):
    raw = "```json" + chr(10) + polish_reply(REC1, FIX1) + chr(10) + "```"
    assert fixtalk.polish(REC1, SENS, gw(tmp_path, raw)[0])["polished"]


def test_fix_shown_must_be_in_both_texts(tmp_path):
    raw = json.dumps({"text": REC1.replace("根幹重点", "根管充填"),
                      "fixes": [{"from": "根幹重点", "to": "根管充填"}, {"from": "話に無い", "to": "根管充填"},
                                {"from": "肺脳", "to": "本文に無い言葉"}, 5, {"from": "x"}], "doubts": []}, ensure_ascii=False)
    res = fixtalk.polish(REC1, SENS, gw(tmp_path, raw)[0])
    assert [f["from"] for f in res["fixes"]] == ["根幹重点"] and res["polished"]  # 形の崩れた直しは、その1つだけ捨てる（本文は使う）


# ---- 書き方の統一（仮歯は TeC。表記だけ。プログラムが置き換える） ----

def test_tec_spelling_applies_after_polish(tmp_path):
    res = fixtalk.polish(REC2, SENS, gw(tmp_path, polish_reply(REC2, [("次第地駆動", "支台築造")]))[0])
    assert res["text"] == "右下6番の支台築造の形成をしました。仮歯はTeCを入れました。"
    assert {"from": "TEK", "to": "TeC", "by": "rule"} in res["fixes"]


@pytest.mark.parametrize("before,after", [
    ("仮歯はTEKを入れた", "仮歯はTeCを入れた"), ("ＴＥＫを外した", "TeCを外した"), ("テックを入れた", "TeCを入れた"),
    ("tekで様子を見る", "TeCで様子を見る"), ("TEKとテックを", "TeCとTeCを"),
])
def test_tec_spelling(before, after):
    assert fixtalk.normalize_spellings(before)[0] == after


@pytest.mark.parametrize("keep", ["テックスという言葉", "ATEKA", "TEKS", "ハイテック製"])
def test_tec_spelling_does_not_touch_other_words(keep):
    assert fixtalk.normalize_spellings(keep)[0] == keep


def test_mishearing_words_are_examples_not_replacement_rules():
    cfg = json.loads((ROOT / "config" / "dental_terms.json").read_text(encoding="utf-8"))
    assert "根幹重点" in cfg["readings"]["根管充填"] and "肩を取" in cfg["readings"]["型を取"]
    assert fixtalk.normalize_spellings("根幹重点と肩を取と高圧剤")[0] == "根幹重点と肩を取と高圧剤"  # 置き換えには使わない
    assert "根幹重点→根管充填" in fixtalk.examples() and "高圧剤→降圧剤" in fixtalk.examples()


def test_finish_text_gives_punctuation_and_tec():
    assert fixtalk.finish_text("仮歯のTEKを入れる") == "仮歯のTeCを入れる。"
    assert fixtalk.finish_text("根管充填をした。") == "根管充填をした。"
    assert fixtalk.finish_text("  ") == ""


def test_organize_prompt_asks_for_punctuation_and_tec():
    assert "句読点" in memo.SYSTEM and "TeC" in memo.SYSTEM and "TEK とは書きません" in memo.SYSTEM


# ---- 5つに分ける（清書に対して、話していないことは足さない）----

def reply_for(text_done, quote):
    return json.dumps({**{k: [] for k in memo.KEYS}, "done": [{"text": text_done, "quote": quote}]}, ensure_ascii=False)


def test_items_are_made_from_polished_text_and_quotes_checked_against_it(tmp_path):
    polished = "今日は右下6番の根管充填をしました。"
    ok = reply_for("右下6番の根管充填", "右下6番の根管充填をしました")
    items = memo.organize(polished, SENS, Gateway(mouth=ScriptedMouth(ok), log_dir=tmp_path / "log"))
    assert items["done"] == [{"text": "右下6番の根管充填。", "quote": "右下6番の根管充填をしました"}]
    # 聞き違いのままの抜き出しは、清書には無いので捨てる
    old = reply_for("右下6番の根管充填", "右下6番の根幹重点をしました")
    assert memo.organize(polished, SENS, Gateway(mouth=ScriptedMouth(old), log_dir=tmp_path / "log"))["done"] == []


def test_untalked_treatment_is_not_added(tmp_path):
    made_up = json.dumps({**{k: [] for k in memo.KEYS},
                          "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"},
                                   {"text": "抜歯をした", "quote": "抜歯をしました"}]}, ensure_ascii=False)
    items = memo.organize("今日は右下6番の根管充填をしました。", SENS, Gateway(mouth=ScriptedMouth(made_up), log_dir=tmp_path / "log"))
    assert [r["text"] for r in items["done"]] == ["右下6番の根管充填。"] and "抜歯" not in memo.body_lines(items)


def test_same_items_are_merged_into_one():
    talk = "今日は右下6番の根管充填をしました。今日は右下6番の根管充填をしました。"
    row = {"text": "右下6番の根管充填。", "quote": "右下6番の根管充填をしました"}
    raw = json.dumps({**{k: [] for k in memo.KEYS}, "done": [row, dict(row)]}, ensure_ascii=False)
    assert len(memo.parse_items(raw, talk)["done"]) == 1


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
