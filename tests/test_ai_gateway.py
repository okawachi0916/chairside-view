"""G15: 送信の1か所化と伏字の試験。本物の Claude は呼ばない（偽物の口）。"""
import json
import re
import threading
from pathlib import Path

import pytest

from app.ai.gateway import Gateway, sensitive_from_db
from app.ai.redact import Patient, RedactionFailed, Sensitive, Table

ROOT = Path(__file__).resolve().parents[1]

TARO = Patient(name="見本 太郎", kana="みほん たろう", chart_no="100023", phone="090-1234-5678",
               address="架空県見本市中央1-2-3", birth_date="1980-05-12")
HANAKO = Patient(name="見本 花子", kana="みほん はなこ", chart_no="100024", phone="03-1111-2222",
                 address="架空県見本市東4-5-6", birth_date="1991-11-03")
SENS = Sensitive(patients=[TARO, HANAKO], staff=["衛生 次郎"], clinics=["見本歯科クリニック"])

SECRET_PARTS = ["見本", "太郎", "花子", "みほん", "たろう", "100023", "090-1234-5678",
                "架空県見本市", "衛生", "次郎", "見本歯科クリニック", "1980"]


class Echo:
    """送られた文をそのまま返す偽物の口。"""

    def __init__(self):
        self.sent = []

    def complete(self, system, user, max_tokens):
        self.sent.append((system, user))
        return user


def gw(tmp_path, mouth=None, **kw):
    return Gateway(mouth=mouth or Echo(), log_dir=tmp_path / "log", **kw)


WRITINGS = [
    "見本 太郎さんが来ました",
    "見本　太郎さんが来ました",
    "見本太郎さんが来ました",
    "見本 太郎様のカルテ",
    "見本さんは右下が痛い",
    "太郎さんは右下が痛い",
    "太郎君",
    "みほん たろう",
    "みほんたろう",
    "ミホン タロウ",
    "ミホンタロウ",
    "カルテ番号 100023",
    "カルテ番号 １０００２３",
    "電話 090-1234-5678",
    "電話 09012345678",
    "電話 ０９０－１２３４－５６７８",
    "住所 架空県見本市中央1-2-3",
    "住所 架空県見本市中央１－２－３",
    "生年月日 1980-05-12",
    "生年月日 1980/05/12",
    "生年月日 1980年5月12日",
    "生年月日 1980年05月12日",
    "生年月日 昭和55年5月12日",
    "衛生 次郎さんが担当",
    "衛生次郎",
    "次郎さん",
    "見本歯科クリニックから紹介",
    "見本​太郎さん",
    "見 本 太 郎",
]


@pytest.mark.parametrize("text", WRITINGS)
def test_each_writing_is_masked_and_restored(tmp_path, text):
    g = gw(tmp_path)
    r = g.send(text, SENS)
    sent = g.mouth.sent[0][1]
    for part in SECRET_PARTS:
        assert part not in sent, (text, sent)
    assert "[" in sent
    assert r.text == text


def test_writings_count():
    assert len(WRITINGS) >= 20


def test_same_family_name_restores_correctly(tmp_path):
    g = gw(tmp_path)
    text = "見本 太郎さんと見本 花子さん、見本さんの姉"
    r = g.send(text, SENS)
    sent = g.mouth.sent[0][1]
    assert "[氏名1]" in sent and "[氏名2]" in sent and "[姓1]" in sent
    assert r.text == text


def test_longer_strings_first():
    t = Table(SENS)
    out = t.mask("見本 太郎")
    assert out == "[氏名1]"  # [姓1][名1] に割れない


def test_number_marks_per_kind(tmp_path):
    t = Table(SENS)
    out = t.mask("100023 と 100024")
    assert out == "[番号1] と [番号2]"
    assert t.restore(out) == "100023 と 100024"


def test_leftover_stops_sending(tmp_path):
    class Leaky(Table):
        def mask(self, text):  # わざと名前を残す伏字
            return super().mask(text).replace("[姓1]", "見本")

    mouth = Echo()
    g = gw(tmp_path, mouth, masker=Leaky)
    with pytest.raises(RedactionFailed) as e:
        g.send("見本さんが来た", SENS)
    assert "伏字に失敗しました" in str(e.value)
    assert mouth.sent == []
    assert not (tmp_path / "log").exists() or not list((tmp_path / "log").glob("*.jsonl"))


def test_no_mask_at_all_stops_sending(tmp_path):
    class Broken(Table):
        def mask(self, text):
            return text

    mouth = Echo()
    with pytest.raises(RedactionFailed):
        gw(tmp_path, mouth, masker=Broken).send("太郎さん", SENS)
    assert mouth.sent == []


def test_restore_equals_original_for_mixed_text(tmp_path):
    text = "今日は見本　太郎さん（みほん たろう、1980/05/12、090-1234-5678）。見本 太郎さんは衛生 次郎が診ます。"
    r = gw(tmp_path).send(text, SENS, system="担当は衛生 次郎。")
    assert r.text == text


def test_sent_log_has_masked_text_only(tmp_path):
    g = gw(tmp_path)
    g.send("見本 太郎さん", SENS, purpose="test")
    files = list((tmp_path / "log").glob("*.jsonl"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    row = json.loads(body.splitlines()[0])
    assert row["user"] == "[氏名1]さん" and row["purpose"] == "test"
    assert "見本" not in body and "太郎" not in body


def test_two_senders_at_once_do_not_mix(tmp_path):
    s1 = Sensitive(patients=[Patient(name="甲野 一郎")])
    s2 = Sensitive(patients=[Patient(name="乙川 二郎")])
    barrier = threading.Barrier(2)

    class Slow:
        def complete(self, system, user, max_tokens):
            barrier.wait(timeout=5)  # 2つが同時に口へ着いてから返す
            return user

    g = gw(tmp_path, Slow())
    out = {}

    def run(key, text, sens):
        out[key] = g.send(text, sens).text

    t1 = threading.Thread(target=run, args=("a", "甲野 一郎さん", s1))
    t2 = threading.Thread(target=run, args=("b", "乙川 二郎さん", s2))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert out == {"a": "甲野 一郎さん", "b": "乙川 二郎さん"}


def test_unknown_marks_from_claude_are_left(tmp_path):
    class Mouth:
        def complete(self, system, user, max_tokens):
            return "[氏名1]さんと[氏名9]さん"

    r = gw(tmp_path, Mouth()).send("見本 太郎", SENS)
    assert r.text == "見本 太郎さんと[氏名9]さん"


def test_error_does_not_leak_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAIRSIDE_CLAUDE_KEY", "sk-test-secret-999")

    class Bad:
        def complete(self, system, user, max_tokens):
            raise ValueError("bad key sk-test-secret-999")

    with pytest.raises(RuntimeError) as e:
        gw(tmp_path, Bad()).send("こんにちは", SENS)
    assert "sk-test-secret-999" not in str(e.value) and "sk-test-secret-999" not in repr(e.value.__cause__)


def test_sensitive_from_db_masks_seeded_patients(tmp_path):
    import os
    import subprocess
    import sys

    env = {**os.environ, "CV_DATA_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], env=env, capture_output=True)
    assert r.returncode == 0
    from app.db import connect

    con = connect(tmp_path / "app.db")
    sens = sensitive_from_db(con)
    assert len(sens.patients) == 5
    rows = con.execute("SELECT name, chart_no, birth_date FROM patients").fetchall()
    g = gw(tmp_path / "x")
    for row in rows:
        text = f"{row['name']}さん（{row['chart_no']}、{row['birth_date']}）"
        out = g.send(text, sens)
        sent = g.mouth.sent[-1][1]
        assert row["chart_no"] not in sent and row["name"] not in sent and row["birth_date"] not in sent
        assert out.text == text


def test_only_gateway_imports_anthropic():
    for p in (ROOT / "app").rglob("*.py"):
        if p.name in ("gateway.py",):
            continue
        assert not re.search(r"^\s*(import|from)\s+anthropic", p.read_text(encoding="utf-8"), re.M), p
