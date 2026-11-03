"""G21d: 見本データに本物の名前を使わない。すでに入っているデータベースも新しい名前になる。"""
import sqlite3
import subprocess

from app.db import update as upd, initial


def test_initial_data_has_no_real_names():
    text = repr(initial.build())
    assert "大川内" not in text and "田中" not in text
    assert "山本" in text and "佐藤" in text


def test_update_renames_staff_in_existing_db(tmp_path):
    p = tmp_path / "a.db"
    upd.update(str(p))
    con = sqlite3.connect(p)
    con.execute("UPDATE appointments SET staff_name='大川内' WHERE id=(SELECT MIN(id) FROM appointments)")
    con.execute("UPDATE appointments SET staff_name='田中' WHERE id=(SELECT MAX(id) FROM appointments)")
    con.commit(); con.close()
    upd.update(str(p))
    con = sqlite3.connect(p)
    names = {r[0] for r in con.execute("SELECT staff_name FROM appointments")}
    con.close()
    assert "大川内" not in names and "田中" not in names


def test_no_real_names_in_tracked_files():
    out = subprocess.run(["git", "grep", "-l", "-e", "大川内", "-e", "田中", "--", ".",
                          ":!docs/制作記録.md", ":!docs/総点検.md", ":!tests/test_sample_names.py",
                          ":!app/db/update.py", ":!docs/仕様.md"], capture_output=True, text=True, encoding="utf-8").stdout
    assert out.strip() == "", out
