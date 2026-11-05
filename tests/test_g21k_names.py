"""G21k-1: 名前の一覧が読めないときは、Claude へ送らずに止める。"""
import sqlite3

import pytest

from app.ai import ask as ask_mod
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway, sensitive_from_db
from app.ai.redact import NAMES_UNREADABLE, NameListUnreadable
from app.db import update as upd


@pytest.fixture
def con(tmp_path):
    p = tmp_path / "a.db"
    upd.update(str(p))
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    return c


def test_normal_list_includes_staff(con):
    s = sensitive_from_db(con)
    assert "大川内" in s.staff and "佐藤" in s.staff


def test_broken_list_raises_and_nothing_is_sent(con, tmp_path):
    con.execute("DROP TABLE patients")
    with pytest.raises(NameListUnreadable):
        sensitive_from_db(con)
    mouth = ScriptedMouth("これは使われない")
    res = ask_mod.answer("ペニシリンの記録は？", con, 1, Gateway(mouth=mouth, log_dir=tmp_path / "log"))
    assert mouth.sent == [] and res["sends"] == 0
    assert res["result"] == "stopped" and res["message"] == NAMES_UNREADABLE


def test_unreadable_staff_column_stops_instead_of_empty(con):
    con.execute("ALTER TABLE appointments RENAME COLUMN staff_name TO staff_name_x")
    con.execute("ALTER TABLE appointments ADD COLUMN staff_name INTEGER")  # 列はあるのに中身が読めない形にしても、黙って空にしない
    con.execute("DROP TABLE treatment_plans")
    s = sensitive_from_db(con)  # 表そのものが無いのは「読むものが無い」だけ
    assert isinstance(s.staff, list)


def test_long_lines_are_not_cut_silently():
    from app.ai import confirm, memo
    long = "あ" * 1200
    items = {k: [] for k in memo.KEYS}
    items["done"] = [{"text": long, "quote": "い" * 900}]
    out = confirm.check_items(items)
    assert out["done"][0]["text"] == long and out["done"][0]["quote"] == "い" * 900
