"""G19k: 聞き取りのすぐ後の清書。画面の本文は清書（直した言葉に下線・迷う言葉に印）、聞き取りのままは押すと開く。
要約は清書から作る。清書が失敗しても止まらない。送信1回ごとの時間切れ。偽物の口。"""
import json
import time

from app.ai import fixtalk, recpipe
from app.ai.fake import ScriptedMouth
from tests.polish_helper import MISHEAR, fixer, polish_reply
from tests.test_g19b import MouthFor, manual, reply_for, segment  # noqa: F401
from tests.test_rec_pipeline import EMPTY, api, appt_of, con_of, env, use, wait_state  # noqa: F401

T = "今日は右下6番の根幹重点をしました。"


def view(env, appt):  # noqa: F811
    return api(env, "get", f"/api/view/unit?appt={appt}&role=doctor")[1]["html"]


def test_segment_is_polished_right_after_transcription(manual):  # noqa: F811
    mouth = use(manual, MouthFor(EMPTY), T)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, T)
    r = recpipe.get(con_of(manual), rid)
    assert r["transcript"] == T and r["polished"] == "今日は右下6番の根管充填をしました。"  # 聞き取りのままと清書は別に持つ
    assert recpipe.polish_of(r)["fixes"] == [{"from": "根幹重点", "to": "根管充填", "by": "claude"}]
    assert len(mouth.polish_sent) == 1 and mouth.sent == []  # 清書だけ送った（要約はまだ）
    # 患者様の今日の予定などを手がかりとして渡している（名前は伏字）
    system = mouth.polish_sent[0][0]
    assert "今日の予約の処置:" in system and "治療計画:" in system and "直近の治療歴:" in system
    assert "見本" not in system and "花子" not in system


def test_screen_shows_polished_text_underlined_and_original_on_demand(manual):  # noqa: F811
    use(manual, MouthFor(EMPTY), T)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, T)
    html = view(manual, a)
    i = html.index(f'data-seg-id="{rid}"')
    seg = html[i:html.index("</details>", i) + len("</details>")]
    assert '<p class="seg-text" data-part="seg-text">今日は右下6番の<u class="pf-fix">根管充填</u>をしました。</p>' in seg
    assert '<details class="seg-raw"><summary>聞き取りのまま</summary><p>' + T + "</p></details>" in seg
    code, d = api(manual, "get", f"/api/segments?appt={a}")
    mine = next(s for s in d["segments"] if s["id"] == rid)
    assert mine["text"] == "今日は右下6番の根管充填をしました。" and mine["raw"] == T and mine["polished"] is True
    assert mine["fixes"][0]["to"] == "根管充填"


def test_doubtful_words_are_marked(manual):  # noqa: F811
    talk = "左下6番はキョウザンをしました。"
    use(manual, ScriptedMouth(EMPTY, polish_reply=polish_reply(talk, [], doubts=["キョウザン"])), talk)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, talk)
    html = view(manual, a)
    assert '<mark class="pf-doubt">キョウザン</mark>' in html[html.index(f'data-seg-id="{rid}"'):]


def test_failed_polish_goes_on_with_the_transcript_and_says_so(manual):  # noqa: F811
    use(manual, ScriptedMouth(EMPTY, polish_reply="壊れた応答"), T)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, T)  # 文字起こし済みまで進む（止まらない）
    r = recpipe.get(con_of(manual), rid)
    assert r["state"] == "文字起こし済み" and r["polished"] == "" and recpipe.polish_of(r)["note"] == fixtalk.NOTE_FAILED
    html = view(manual, a)
    assert "清書できませんでした" in html and T in html and "聞き取りのまま</summary>" not in html[html.index(f'data-seg-id="{rid}"'):]
    # 要約は聞き取りのままで作れる
    assert api(manual, "post", f"/rec/{rid}/summarize")[0] == 200
    assert wait_state(manual, rid, ["下書き", "失敗"])["state"] == "下書き"


def test_polish_with_changed_digits_is_not_used(manual):  # noqa: F811
    use(manual, ScriptedMouth(EMPTY, polish_reply=polish_reply(T, [], text=T.replace("6番", "7番"))), T)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, T)
    r = recpipe.get(con_of(manual), rid)
    assert r["polished"] == "" and recpipe.polish_of(r)["note"] == fixtalk.NOTE_DIGITS
    assert fixtalk.NOTE_DIGITS in view(manual, a)


def test_summary_is_made_from_the_polished_text(manual):  # noqa: F811
    mouth = use(manual, MouthFor(reply_for(("右下6番の根管充填。", "根管充填をしました"))), T)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, T)
    assert api(manual, "post", f"/rec/{rid}/summarize")[0] == 200
    r = wait_state(manual, rid, ["下書き", "失敗"])
    assert r["state"] == "下書き", r["error"]
    assert "根管充填をしました" in mouth.sent[0][1] and "根幹重点" not in mouth.sent[0][1]
    assert len(mouth.polish_sent) == 1  # 要約のときに、清書し直さない
    c = con_of(manual)
    d = c.execute("SELECT * FROM drafts WHERE id = ?", (r["draft_id"],)).fetchone()
    assert d["transcript"] == T and d["fixed_transcript"] == "今日は右下6番の根管充填をしました。"
    assert json.loads(d["fixes"])[0]["from"] == "根幹重点" and d["polish_note"] == ""
    page = manual["client"].get(f"/drafts/{r['draft_id']}").text
    assert '<u class="pf-fix">根管充填</u>' in page and "data-part='draft-raw'" in page and "聞き取りのまま" in page
    assert page.index("data-part='draft-polished'") < page.index("data-part='draft-raw'")  # 本文が先、聞き取りのままは後
    api_d = api(manual, "get", f"/api/drafts/{r['draft_id']}")[1]
    assert api_d["doubts"] == [] and api_d["polish_note"] == ""


def test_human_edited_text_is_not_polished_again(manual):  # noqa: F811
    mouth = use(manual, MouthFor(reply_for(("右下6番の根幹重点。", "根幹重点をしました"))), T)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, T)
    assert len(mouth.polish_sent) == 1
    assert api(manual, "post", f"/rec/{rid}/reorganize", json={"transcript": "今日は右下6番の根幹重点をしました。"})[0] == 200
    r = wait_state(manual, rid, ["下書き", "失敗"])
    assert r["state"] == "下書き"
    assert len(mouth.polish_sent) == 1 and r["fix_off"] == 1 and r["polished"] == ""  # 人が直した文字は、自動で直さない


def test_each_send_has_its_own_time_limit(manual):  # noqa: F811
    """送信1回ごとに時間を数える。清書が区切りごとに増えても、まとめの要約が時間切れにならない。"""
    manual["mp"].setenv("CHAIRSIDE_AI_TIMEOUT", "1.0")

    def slow(talk):
        time.sleep(0.6)
        return polish_reply(talk, [])

    mouth = use(manual, ScriptedMouth(reply_for(("右下6番の根管充填。", "根管充填をしました")), delay_ms=600, polish_reply=slow), T)
    a = appt_of(manual, "0123")
    ids = [segment(manual, a, T + "その" + str(i) + "。") for i in range(3)]   # 清書3回で 1.8 秒（全体で数えると 1 秒を超える）
    assert api(manual, "post", "/rec/combine", json={"appt": a})[0] == 200
    for i in ids:
        assert wait_state(manual, i, ["下書き", "失敗"], 15)["state"] == "下書き"
    # 1回の送信が長過ぎるときは、その送信が時間切れ
    mouth.delay_ms = 1800
    ids2 = [segment(manual, a, "もう1つの区切りです。")]
    assert api(manual, "post", "/rec/combine", json={"appt": a})[0] == 200
    r = wait_state(manual, ids2[0], ["文字起こし済み", "失敗"], 15)
    assert "時間切れ" in r["error"]


def test_polish_timeout_does_not_stop_the_recording(manual):  # noqa: F811
    manual["mp"].setenv("CHAIRSIDE_AI_TIMEOUT", "0.3")

    def very_slow(talk):
        time.sleep(1.0)
        return polish_reply(talk, [])

    use(manual, ScriptedMouth(EMPTY, polish_reply=very_slow), T)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, T)
    r = recpipe.get(con_of(manual), rid)
    assert r["state"] == "文字起こし済み" and r["polished"] == "" and recpipe.polish_of(r)["note"] == fixtalk.NOTE_FAILED
    time.sleep(1.0)


def test_polish_uses_the_model_set_for_polish():
    from app.ai.settings import load_model

    assert load_model("polish") and load_model("polish") == load_model()  # 実測で決めた（docs/清書のモデル比べ.md）。名前は config にだけある
    cfg = json.loads((recpipe.Path(__file__).resolve().parents[1] / "config" / "model.json").read_text(encoding="utf-8"))
    assert cfg["purposes"]["polish"] and cfg["polish_candidates"]
