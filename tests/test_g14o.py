"""G14o: 聞き違いの表（config/mishear.json）。声の操作の照合だけに効き、録音の文字起こしなどには混ざらない。Claude は使わない。"""
import json
import re
from pathlib import Path

import pytest

import app.voice.interpret as I
from app import numbering
from app.voice.interpret import FAILED, OP, UNRELATED, interpret

ROOT = Path(__file__).resolve().parents[1]
TABLE = json.loads((ROOT / "config" / "mishear.json").read_text(encoding="utf-8"))
RESULTS = json.loads((ROOT / "tests" / "mishear_measure" / "results.json").read_text(encoding="utf-8"))["結果"]


def same_op(a, b):
    def k(r):
        n = str(r["numbers"][0]) if r.get("numbers") else (str(r["arg"]) if r.get("arg") is not None else None)
        return (r["kind"], r.get("action"), n)
    return k(a) == k(b)


def test_table_shape_and_sources():
    """3つの表があり、どの行にも 聞こえ方・正しくは・出どころ がある。予想と実測の両方がある。"""
    for name in ("番号の言い方", "番の聞こえ方", "操作の言葉の聞こえ方"):
        assert TABLE[name], name
        for r in TABLE[name]:
            assert r["聞こえ方"] and r["正しくは"] and r["出どころ"] in ("予想", "実測"), r
    sources = {r["出どころ"] for name in ("番号の言い方", "番の聞こえ方", "操作の言葉の聞こえ方") for r in TABLE[name]}
    assert sources == {"予想", "実測"}


def test_table_rows_all_work():
    """番号の言い方×番の聞こえ方の全部の組み合わせが、正しい番号になる。"""
    for n in TABLE["番号の言い方"]:
        for b in TABLE["番の聞こえ方"]:
            res = interpret(n["聞こえ方"] + b["聞こえ方"])
            assert res["kind"] == OP and res["action"] == "part-number", (n, b)
            got = res["numbers"][0] if res.get("numbers") else res["arg"]
            assert int(got) == int(n["正しくは"]), (n, b, res)


@pytest.mark.parametrize("heard,want", [("7ば", 7), ("7バン", 7), ("7晩", 7), ("七盤", 7), ("ななば", 7), ("ナナバン", 7),
                                        ("1ば", 1), ("いちば", 1), ("2ば", 2), ("3つ外", 3), ("4つ目", 4), ("ログマン", 6),
                                        ("きゅうば", 9), ("給付外", 9), ("じゅうば", 10), ("12ば", 12), ("7ばを開いて", 7), ("7ばです", 7)])
def test_number_mishearings(heard, want):
    res = interpret(heard)
    assert res["kind"] == OP and res["action"] == "part-number"
    assert int(res["numbers"][0] if res.get("numbers") else res["arg"]) == want


def test_short_forms_do_not_react():
    """「いち」だけ・「ば」だけのような短い形では動かない。"""
    for w in ["いち", "に", "さん", "なな", "ば", "バン", "晩", "つ外", "ログ", "キュー", "よ", "ご視聴ありがとうございました"]:
        assert interpret(w)["action"] is None, w


def test_shichi_and_shi_not_added():
    """4 と 7 は取り違えやすいので「し」「しち」は表に入れない（仕様）。"""
    for w in ["しば", "しちば", "しばん", "しちばん"]:
        assert interpret(w)["action"] is None, w


def test_ordinary_talk_does_not_act():
    talk = ["今日はいい天気ですね", "七日間様子を見ます", "痛みはありますか", "次回は来週にしましょう", "お薬は出していません",
            "三つ目の歯が痛いです", "ばんそうこうを貼ります", "晩ごはんは食べました", "一番奥の歯です", "新しい盤を作ります"]
    for t in talk:
        assert interpret(t)["action"] is None, t


def test_measured_mishearings_resolve():
    """実測で出た聞き違いのうち、言葉として読めるものは言った操作になる。残るのは空・「に」だけ・無音の幻などだけ。"""
    bad = []
    total = 0
    for x in RESULTS:
        want = interpret(x["言った"])
        if want["kind"] != OP:
            continue
        total += 1
        if not same_op(interpret(x["聞こえた"]), want):
            bad.append((x["言った"], x["聞こえた"]))
    assert total > 1000
    assert len(bad) <= 60, len(bad)
    assert total - len(bad) > 1200
    for _, heard in bad:  # 通らなかったものは、操作の言葉に似ていないもの（短い・空・無音のときの幻）に限る
        assert not interpret(heard)["action"], heard


def test_table_helps_versus_off(monkeypatch):
    on = sum(1 for x in RESULTS if same_op(interpret(x["聞こえた"]), interpret(x["言った"])))
    monkeypatch.setattr(I, "mishear_variants", lambda s: [])
    off = sum(1 for x in RESULTS if same_op(interpret(x["聞こえた"]), interpret(x["言った"])))
    assert on > off + 300


def test_talk_results_same_with_and_without_table(monkeypatch):
    """普通の言葉・無関係な言葉の結果は、表があってもなくても同じ。"""
    texts = [x["聞こえた"] for x in RESULTS] + ["今日の予約を教えて", "いいえ", "はい", "あのー", "うーん", "お疲れさまです"]
    with_t = {t: interpret(t) for t in texts if interpret(t)["kind"] != OP}
    monkeypatch.setattr(I, "mishear_variants", lambda s: [])
    for t, r in with_t.items():
        assert interpret(t) == r, t


def test_original_word_wins_over_table():
    """元の聞き取りが表の言葉に合うなら、表の候補より先にそれが使われる（今までの動きは変わらない）。"""
    for w, act in [("1番", "part-number"), ("次のページ", "fs-next"), ("戻して", "fs-close"), ("拡大して", None)]:
        assert interpret(w)["action"] == act or act is None


def test_skip_5_and_8_rule_intact():
    """5 と 8 を飛ばす決まりは numbering.py の1か所のまま。聞き違いの表は番号の値を変えるだけで、飛ばす決まりには触れない。"""
    assert [numbering.label(i) for i in range(1, 8)] == [1, 2, 3, 4, 6, 7, 9]
    assert numbering.seq_of(5) is None and numbering.seq_of(8) is None
    assert "5" not in re.sub(r"\s", "", Path(ROOT / "app" / "numbering.py").read_text(encoding="utf-8").split("SKIP =")[1].split("\n")[0].replace("{5, 8}", ""))
    a, b = interpret("ごば"), interpret("5番")
    assert a["action"] == b["action"] and a["numbers"] == b["numbers"] == [5]  # 5番は表で作られても、画面側で「その番号はありません」になる


def test_table_used_only_by_voice_operation():
    """表（mishear）を読むのは interpret.py だけ。録音の文字起こし・整理・下書き・聞き違い直しのコードは表を読まない。"""
    users = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "app").rglob("*.py") if "mishear" in p.read_text(encoding="utf-8") and p.name != "mishear.py")
    assert users == [str(Path("app/voice/interpret.py"))], users
    assert not list((ROOT / "app").rglob("*.js")) or all("mishear" not in p.read_text(encoding="utf-8") for p in (ROOT / "app").rglob("*.js"))


def test_not_shown_in_word_list():
    """言える言葉の一覧（/voice/words）に聞き違いの表は出ない。"""
    from app.routers import voice as V
    src = (ROOT / "app" / "routers" / "voice.py").read_text(encoding="utf-8")
    assert "mishear" not in src
    assert V is not None


def test_runtime_edit_takes_effect(tmp_path, monkeypatch):
    """スタッフが表に1行足すと、読み直しで効く（登録の画面は作らない）。"""
    import app.voice.mishear as M
    t = tmp_path / "mishear.json"
    d = json.loads(json.dumps(TABLE))
    t.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(M, "TABLE", t)
    M._cache.update(mtime=None, data=None)
    assert interpret("7ぼん")["action"] is None
    d["番の聞こえ方"].append({"聞こえ方": "ぼん", "正しくは": "番", "出どころ": "予想"})
    t.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    import os
    os.utime(t, ns=(1, 2_000_000_000_000_000_000))
    assert interpret("7ぼん")["numbers"] == [7]
    M._cache.update(mtime=None, data=None)


def test_missing_table_is_ok(tmp_path, monkeypatch):
    import app.voice.mishear as M
    monkeypatch.setattr(M, "TABLE", tmp_path / "none.json")
    M._cache.update(mtime=None, data=None)
    assert interpret("7番")["numbers"] == [7]
    assert interpret("7ば")["kind"] in (UNRELATED, FAILED)
    M._cache.update(mtime=None, data=None)


def test_confirm_second_word_stays_second_word():
    """確定の2回言う決まり: 「確定」だけは最初の一言にならない（表が「確定」を「確定する」に直さない）。"""
    assert interpret("確定", "draft")["word"] == "(記録|確定)"
    assert interpret("確定する", "draft")["word"] == "確定(する|して)"
    assert interpret("確定すると", "draft")["word"] == "確定(する|して)"
