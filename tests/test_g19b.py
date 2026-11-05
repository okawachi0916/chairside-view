"""G19b: 録音は区切りごとに残し、止めたら文字起こしまで。区切りごとの要約・今日の分をまとめて要約・区切りを消す。
本物の Claude と文字起こしは呼ばない（偽物）。"""
import json
import time

import pytest

from app.ai import memo, recpipe, settings
from app.ai.fake import ScriptedMouth
from tests.polish_helper import MISHEAR, fixer
from tests.test_rec_pipeline import EMPTY, api, appt_of, con_of, env, record, use, wait_state  # noqa: F401

T1 = "今日は右下6番の根幹重点をしました。"
T2 = "右下6番の根幹重点を行いました。次回は二週間後に土台を立てます。"


class MouthFor(ScriptedMouth):
    """清書の応答は、聞き取りの文に出てくる聞き違い（根幹重点など）を直す。"""

    def __init__(self, reply="", **kw):
        super().__init__(reply, polish_reply=fixer(MISHEAR), **kw)


def reply_for(*pairs):
    return json.dumps({**{k: [] for k in memo.KEYS}, "done": [{"text": t, "quote": q} for t, q in pairs]}, ensure_ascii=False)


@pytest.fixture
def manual(env):  # noqa: F811
    """既定どおり、要約は自動で作らない。"""
    env["mp"].setenv("CHAIRSIDE_AUTO_SUMMARY", "0")
    return env


def segment(env, appt, text):  # noqa: F811
    """録音して止め、文字起こしまで済んだ区切りの番号を返す。"""
    env["mp"].setattr(recpipe.fake, "fake_transcript", lambda: text)
    rid = record(env, appt)
    assert api(env, "post", f"/rec/{rid}/transfer", json={})[0] == 200
    r = wait_state(env, rid, ["文字起こし済み", "下書き", "失敗"])
    assert r["state"] == "文字起こし済み", r
    return rid


def test_auto_summary_default_is_false_in_config():
    env_val = None
    import os

    env_val = os.environ.pop("CHAIRSIDE_AUTO_SUMMARY", None)
    try:
        assert settings.auto_summary() is False
        cfg = json.loads(settings.MODEL_JSON.read_text(encoding="utf-8"))
        assert cfg["auto_summary"] is False
    finally:
        if env_val is not None:
            os.environ["CHAIRSIDE_AUTO_SUMMARY"] = env_val


def test_stop_makes_a_segment_without_summary(manual):
    sent = use(manual, MouthFor(EMPTY), T1)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, T1)
    c = con_of(manual)
    r = recpipe.get(c, rid)
    assert r["transcript"] == T1 and r["visit_id"] and r["draft_id"] is None
    assert c.execute("SELECT COUNT(*) FROM drafts WHERE recording_id = ?", (rid,)).fetchone()[0] == 0
    assert sent.sent == [] and len(sent.polish_sent) == 1  # 要約のための送信はしていない（聞き取りのすぐ後の清書だけ送った）


def test_segments_keep_recorded_order_and_link_to_visit(manual):
    use(manual, MouthFor(EMPTY), T1)
    a = appt_of(manual, "0123")
    r1, r2 = segment(manual, a, T1), segment(manual, a, T2)
    c = con_of(manual)
    segs = [s for s in recpipe.segments_of_visit(c, recpipe.get(c, r1)["visit_id"]) if s["id"] in (r1, r2)]  # 見本データの前の日の区切りは除く
    assert [s["id"] for s in segs] == [r1, r2] and [s["transcript"] for s in segs] == [T1, T2]
    code, d = api(manual, "get", f"/api/segments?appt={a}")
    mine = [s for s in d["segments"] if s["id"] in (r1, r2)]
    assert [s["id"] for s in mine] == [r1, r2] and mine[0]["label"] == "まだ要約していません"


def test_summarize_one_segment_uses_only_its_text(manual):
    mouth = use(manual, MouthFor(reply_for(("右下6番の根管充填。", "根管充填をしました"))), T1)
    a = appt_of(manual, "0123")
    r1, r2 = segment(manual, a, T1), segment(manual, a, T2)
    assert api(manual, "post", f"/rec/{r1}/summarize")[0] == 200
    r = wait_state(manual, r1, ["下書き", "失敗"])
    assert r["state"] == "下書き", r["error"]
    assert T2 not in mouth.sent[0][1] and "根管充填" in mouth.sent[0][1]  # 直した文字を送る（根幹重点→根管充填）
    assert recpipe.get(con_of(manual), r2)["state"] == "文字起こし済み"  # 他の区切りは触らない


def test_combine_makes_one_summary_and_replaces_segment_summaries(manual):
    mouth = use(manual, MouthFor(reply_for(("右下6番の根管充填。", "根管充填をしました"))), T1)
    a = appt_of(manual, "0123")
    r1 = segment(manual, a, T1)
    assert api(manual, "post", f"/rec/{r1}/summarize")[0] == 200
    wait_state(manual, r1, ["下書き"])
    first_draft = recpipe.get(con_of(manual), r1)["draft_id"]
    r2 = segment(manual, a, T2)
    mouth.sent.clear()
    mouth.polish_sent.clear()

    mouth.reply = reply_for(("右下6番の根管充填。", "根管充填を行いました"))
    code, body = api(manual, "post", "/rec/combine", json={"appt": a})
    assert code == 200 and body["ids"] == [r1, r2]
    for r in (r1, r2):
        assert wait_state(manual, r, ["下書き", "失敗"])["state"] == "下書き"
    c = con_of(manual)
    d1, d2 = (recpipe.get(c, r)["draft_id"] for r in (r1, r2))
    assert d1 == d2
    assert c.execute("SELECT COUNT(*) FROM drafts WHERE recording_id = ? AND combined = 0", (r1,)).fetchone()[0] == 0  # 区切りごとの要約は置き換え
    d = c.execute("SELECT * FROM drafts WHERE id = ?", (d1,)).fetchone()
    assert d["combined"] == 1 and d["status"] == "draft" and d["recording_id"] == r2
    assert d["transcript"] == T1 + "\n" + T2  # 録音した順に、話したままの文字を残す
    assert "根管充填" in d["fixed_transcript"] and "根幹重点" not in d["fixed_transcript"]  # 聞き違いを直す段を通っている
    system, user = mouth.sent[0]
    assert "録音した順" in system and "後の言い方" in system
    assert user.index("根管充填をしました") < user.index("二週間後")
    assert mouth.polish_sent == []  # まとめるときは清書し直さない（区切りごとに、聞き取りのすぐ後で清書してある）
    assert c.execute("SELECT COUNT(*) FROM drafts WHERE visit_id = ? AND status = 'draft' AND recording_id IS NOT NULL",
                     (recpipe.get(c, r1)["visit_id"],)).fetchone()[0] == 1


def test_combined_summary_is_made_from_the_polished_segments(manual):
    """肺脳・次第蓄造・次第地駆動・根幹重点は、区切りの清書で直っていて、要約に出る。"""
    text = "根幹重点をしました。肺脳があり洗浄しました。次第蓄造と次第地駆動の話もしました。"
    fixed = "根管充填をしました。排膿があり洗浄しました。支台築造と支台築造の話もしました。"
    reply = reply_for(("根管充填をした。", "根管充填をしました"), ("排膿があり洗浄した。", "排膿があり洗浄しました"))
    use(manual, MouthFor(reply), text)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, text)
    assert api(manual, "post", "/rec/combine", json={"appt": a})[0] == 200
    r = wait_state(manual, rid, ["下書き", "失敗"])
    assert r["state"] == "下書き", r["error"]
    d = con_of(manual).execute("SELECT * FROM drafts WHERE id = ?", (r["draft_id"],)).fetchone()
    assert d["fixed_transcript"] == fixed
    for bad in ("根幹重点", "肺脳", "次第蓄造", "次第地駆動"):
        assert bad not in d["body"]


def test_combine_failure_returns_segments(manual):
    class Boom(ScriptedMouth):
        def complete(self, system, user, max_tokens, purpose=""):
            raise RuntimeError("boom")

    use(manual, Boom(EMPTY), T1)
    a = appt_of(manual, "0123")
    rid = segment(manual, a, T1)
    assert api(manual, "post", "/rec/combine", json={"appt": a})[0] == 200
    t0 = time.time()
    while time.time() - t0 < 10 and recpipe.get(con_of(manual), rid)["state"] == "整理中":
        time.sleep(0.05)
    r = recpipe.get(con_of(manual), rid)
    assert r["state"] == "文字起こし済み" and r["error"]  # もう一度押せる


def test_combine_without_segments_is_refused(manual):
    a = appt_of(manual, "0123")
    code, body = api(manual, "post", "/rec/combine", json={"appt": a})
    assert code in (404, 409) and body["error"]


def test_confirm_combined_records_once_and_removes_all_audio(manual):
    use(manual, MouthFor(reply_for(("右下6番の根管充填。", "根管充填をしました"))), T1)
    a = appt_of(manual, "0123")
    r1, r2 = segment(manual, a, T1), segment(manual, a, T2)
    api(manual, "post", "/rec/combine", json={"appt": a})
    wait_state(manual, r1, ["下書き"])
    wait_state(manual, r2, ["下書き"])
    c = con_of(manual)
    did = recpipe.get(c, r1)["draft_id"]
    items = json.loads(c.execute("SELECT items FROM drafts WHERE id = ?", (did,)).fetchone()[0])
    before = c.execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0]
    code, _ = api(manual, "post", f"/api/drafts/{did}/confirm", json={"items": items})
    assert code == 200
    c = con_of(manual)
    assert c.execute("SELECT COUNT(*) FROM clinical_notes").fetchone()[0] == before + 1
    for r in (r1, r2):
        rec = recpipe.get(c, r)
        assert rec["state"] == "確定" and rec["audio_file"] == ""
        assert not (manual["dir"] / "audio" / f"rec_{r}.webm").exists()


def test_delete_is_immediate_undo_works_then_data_is_gone(manual):
    use(manual, MouthFor(EMPTY), T1)
    a = appt_of(manual, "0123")
    r1, r2 = segment(manual, a, T1), segment(manual, a, "言い間違えた区切りです。")
    audio = manual["dir"] / "audio" / f"rec_{r2}.webm"
    assert audio.exists()
    code, body = api(manual, "post", f"/rec/{r2}/delete")
    assert code == 200 and body["undo_sec"] == 5
    c = con_of(manual)
    assert recpipe.get(c, r2)["state"] == "消した"
    # すぐ消えたことになる: 区切りの一覧に「消しました」で出る。まとめには入らない
    assert [s["deleted"] for s in api(manual, "get", f"/api/segments?appt={a}")[1]["segments"] if s["id"] in (r1, r2)] == [False, True]
    assert [s["id"] for s in recpipe.segments_of_visit(c, recpipe.get(c, r1)["visit_id"]) if s["id"] in (r1, r2)] == [r1]
    # 元に戻す
    assert api(manual, "post", f"/rec/{r2}/undelete")[0] == 200
    assert recpipe.get(con_of(manual), r2)["state"] == "文字起こし済み" and audio.exists()
    # もう一度消して、時間が過ぎたら音声も文字も無い・元に戻せない
    api(manual, "post", f"/rec/{r2}/delete")
    c = con_of(manual)
    c.execute("UPDATE recordings SET deleted_at = ? WHERE id = ?", ("2000-01-01T00:00:00", r2))
    c.commit()
    code, body = api(manual, "post", f"/rec/{r2}/undelete")
    assert code == 409
    c = con_of(manual)
    assert c.execute("SELECT COUNT(*) FROM recordings WHERE id = ?", (r2,)).fetchone()[0] == 0
    assert not audio.exists()


def test_after_delete_combine_uses_only_remaining_segments(manual):
    mouth = use(manual, MouthFor(reply_for(("右下6番の根管充填。", "根管充填をしました"))), T1)
    a = appt_of(manual, "0123")
    r1, r2 = segment(manual, a, T1), segment(manual, a, "言い間違えた区切りです。")
    api(manual, "post", f"/rec/{r2}/delete")
    segment_r3 = segment(manual, a, T2)  # 録音し直し
    mouth.sent.clear()
    code, body = api(manual, "post", "/rec/combine", json={"appt": a})
    assert body["ids"] == [r1, segment_r3]
    wait_state(manual, r1, ["下書き"])
    assert "言い間違えた" not in mouth.sent[0][1]


def test_deleting_a_segment_in_a_combined_draft_drops_that_draft_after_purge(manual):
    use(manual, MouthFor(reply_for(("右下6番の根管充填。", "根管充填をしました"))), T1)
    a = appt_of(manual, "0123")
    r1, r2 = segment(manual, a, T1), segment(manual, a, T2)
    api(manual, "post", "/rec/combine", json={"appt": a})
    wait_state(manual, r1, ["下書き"])
    wait_state(manual, r2, ["下書き"])
    api(manual, "post", f"/rec/{r2}/delete")
    c = con_of(manual)
    c.execute("UPDATE recordings SET deleted_at = ? WHERE id = ?", ("2000-01-01T00:00:00", r2))
    c.commit()
    recpipe.purge_deleted(c)
    c = con_of(manual)
    assert c.execute("SELECT COUNT(*) FROM drafts WHERE combined = 1").fetchone()[0] == 0  # 消した話が入った要約は残さない
    assert recpipe.get(c, r1)["state"] == "文字起こし済み"


def test_cannot_delete_while_working_or_confirmed(manual):
    use(manual, MouthFor(EMPTY), T1)
    a = appt_of(manual, "0123")
    code, r = api(manual, "post", "/rec/start", json={"appt": a})
    code, body = api(manual, "post", f"/rec/{r['id']}/delete")
    assert code == 409


def test_fullscreen_html_lists_segments_in_order_with_buttons(manual):
    use(manual, MouthFor(reply_for(("右下6番の根管充填。", "根管充填をしました"))), T1)
    a = appt_of(manual, "0123")
    r1, r2 = segment(manual, a, T1), segment(manual, a, T2)
    api(manual, "post", f"/rec/{r1}/summarize")
    wait_state(manual, r1, ["下書き"])
    code, d = api(manual, "get", f"/api/view/unit?appt={a}&role=doctor")
    html = d["html"]
    assert code == 200 and "録音の区切り" in html
    assert html.index("区切り 1") < html.index(T1) < html.index("区切り 2") < html.index(T2)
    assert f'data-seg="summarize" data-id="{r2}"' in html and f'data-seg="summarize" data-id="{r1}"' not in html
    assert f'data-seg="delete" data-id="{r1}"' in html and f'data-seg="delete" data-id="{r2}"' in html
    assert 'data-seg="combine"' in html and "今日の分をまとめて要約" in html and "この区切りを要約" in html
    assert "この区切りを消す" in html and "まだ要約していません" in html
    api(manual, "post", f"/rec/{r2}/delete")
    html = api(manual, "get", f"/api/view/unit?appt={a}&role=doctor")[1]["html"]
    assert "元に戻す" in html and f'data-seg="undelete" data-id="{r2}"' in html


def test_names_are_redacted_in_combined_send(manual):
    mouth = use(manual, MouthFor(EMPTY), "見本 花子さん、今日は根管充填をしました。")
    a = appt_of(manual, "0123")
    rid = segment(manual, a, "見本 花子さん、今日は根管充填をしました。")
    api(manual, "post", "/rec/combine", json={"appt": a})
    wait_state(manual, rid, ["下書き", "失敗"])
    for _, user in mouth.sent + mouth.polish_sent:
        assert "見本" not in user and "花子" not in user
