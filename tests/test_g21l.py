"""G21l: 見本の日付が、日が変わっても今日へ合う（間隔は保つ）。
決まりは app/db/dates.py の1か所。起動・日付またぎ・restore のどれでも同じ決まりを通る。"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from app import errlog
from app.db import age_on, connect, dates, schema
from app.db.update import update
from app.today import today
from app.views import data as D

ROOT = Path(__file__).resolve().parent.parent
FIRST = "2026-11-06"  # 見本を作った日（BASE）。conftest も同じ日に止めている


@pytest.fixture
def home(tmp_path, monkeypatch):
    """自分だけのデータベース（見本を 2026-11-06 に合わせた状態）。ほかの試験の data/runtime には触らない。"""
    data = tmp_path / "data"
    monkeypatch.setenv("CV_DATA_DIR", str(data))
    monkeypatch.setenv("CV_TODAY", FIRST)
    monkeypatch.setenv("CV_DEMO_DIR", str(tmp_path / "demo"))  # 控えの置き場は、データの場所と重ならない所
    dates.forget()
    update()
    yield data
    dates.forget()
    D._ready.discard(str(data / "app.db"))


def go(monkeypatch, day):
    monkeypatch.setenv("CV_TODAY", day)


def rel(con):
    """SHIFT の欄の値を、「今日からの日数」と日時の後ろの部分で持つ。日が変わっても、見本との間隔が同じなら同じ形になる。"""
    t = date.fromisoformat(today())
    out = {}
    for table, cols in dates.SHIFT.items():
        for col in cols:
            for rid, v in con.execute(f"SELECT id, {col} FROM {table}"):
                if isinstance(v, str) and re.match(r"\d{4}-\d{2}-\d{2}", v):
                    out[(table, col, rid)] = ((date.fromisoformat(v[:10]) - t).days, v[10:])
    return out


def marker(con):
    return dates.get_marker(con)


def todays(con):
    return [tuple(r) for r in con.execute(
        "SELECT id, patient_id, start_time, role, treatment FROM appointments WHERE appt_date = ? AND status = 'booked' ORDER BY id",
        (today(),))]


# ---------- 1. 日付を進める ----------

def test_sample_follows_today_and_keeps_gaps(home, monkeypatch):
    base_rel = rel(connect())
    base_today = todays(connect())
    assert len(base_today) == 6 and marker(connect()) == FIRST
    births = [r[0] for r in connect().execute("SELECT birth_date FROM patients ORDER BY id")]
    ages = [age_on(b) for b in births]
    for day in ("2026-11-07", "2026-11-10"):
        go(monkeypatch, day)
        con = connect()  # 開いた日が「今日」。開くだけで合う
        assert marker(con) == day
        assert todays(con) == base_today  # 予約一覧の「今日」に、同じ見本の予約が出る
        assert rel(con) == base_rel  # 前回・次回までの日数など、見本との間隔がそのまま
        assert [r[0] for r in con.execute("SELECT birth_date FROM patients ORDER BY id")] == births  # 生年月日は動かない
        assert [age_on(b) for b in births] == ages  # 年齢が変わらない
        con.close()
    # 画面の側も同じ（予約一覧のデータ）
    assert [r["id"] for r in D.today_list()] == [r[0] for r in base_today]


def test_going_back_works_the_same_way(home, monkeypatch):
    base_rel = rel(connect())
    go(monkeypatch, "2026-11-10")
    assert rel(connect()) == base_rel
    go(monkeypatch, "2026-11-08")  # 日付を戻した
    con = connect()
    assert marker(con) == "2026-11-08" and rel(con) == base_rel
    go(monkeypatch, "2026-10-01")  # 大きく戻しても、同じ検査の日が重ならずに動く
    con = connect()
    assert marker(con) == "2026-10-01" and rel(con) == base_rel


def test_second_call_in_the_same_day_does_nothing(home, monkeypatch):
    go(monkeypatch, "2026-11-09")
    con = connect()
    assert dates.align(con) == 0  # すでに今日
    before = rel(con)
    assert dates.align(con) == 0 and rel(con) == before


# ---------- 2. サーバーを動かしたまま日付が変わる ----------

def test_running_server_follows_the_new_day(home, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    first = c.get("/api/today").json()
    assert len(first["rows"]) >= 1
    ids = [r["id"] for r in first["rows"]]
    page1 = c.get(f"/api/view/unit?appt={ids[0]}&role=doctor").text
    assert "2026年11月6日" in page1
    go(monkeypatch, "2026-11-07")  # 夜をまたいだ（サーバーはそのまま）
    second = c.get("/api/today").json()
    assert [r["id"] for r in second["rows"]] == ids  # 次の読み込みで、同じ見本の予約が「今日」に出る
    page2 = c.get(f"/api/view/unit?appt={ids[0]}&role=doctor").text
    assert "2026年11月7日" in page2 and "2026年11月6日" not in page2.split("今日")[0]
    go(monkeypatch, "2026-11-10")
    assert [r["id"] for r in c.get("/api/today").json()["rows"]] == ids


# ---------- 3. 控えを読み込む（restore） ----------

def _state(*args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "demo_state.py"), *args], cwd=ROOT,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"}, capture_output=True, text=True, encoding="utf-8", errors="replace")


def test_restore_aligns_right_after_loading(home, monkeypatch):
    assert _state("save", "g21l").returncode == 0
    go(monkeypatch, "2026-11-10")  # 控えを作った日より後に読み込む
    r = _state("restore", "g21l")
    assert r.returncode == 0, r.stderr
    raw = sqlite3.connect(home / "app.db")  # 画面は開かず、データベースの中身を直接見る
    assert raw.execute("SELECT value FROM app_meta WHERE key = 'dates_aligned_to'").fetchone()[0] == "2026-11-10"
    assert raw.execute("SELECT COUNT(*) FROM appointments WHERE appt_date = '2026-11-10' AND status = 'booked'").fetchone()[0] == 6
    assert raw.execute("SELECT COUNT(*) FROM appointments WHERE appt_date = '2026-11-06'").fetchone()[0] == 0


def test_restore_of_an_old_state_without_marker(home, monkeypatch):
    """印の無い古い控え: 見本の決まった1行から、ずらした日数が分かり、印がつく（控えのファイルには触らない）。"""
    assert _state("save", "old").returncode == 0
    saved = home.parent / "demo" / "old" / "app.db"
    raw = sqlite3.connect(saved)
    raw.execute("DELETE FROM app_meta")  # 古い控えの形（印が無い）にする
    raw.commit()
    raw.close()
    stat = saved.stat().st_mtime_ns
    base_rel = rel(connect())
    go(monkeypatch, "2026-11-09")
    assert _state("restore", "old").returncode == 0
    con = connect()
    assert marker(con) == "2026-11-09" and rel(con) == base_rel
    assert saved.stat().st_mtime_ns == stat  # 控えの中身は変えていない


# ---------- 4. 院長が入れた録音・要約も同じだけ動く。待ち時間の時刻は動かない ----------

def test_own_recordings_move_with_the_sample_but_machine_times_do_not(home, monkeypatch):
    con = connect()
    vid, pid, vday = con.execute("SELECT id, patient_id, visit_date FROM visits WHERE visit_date = ? LIMIT 1", (FIRST,)).fetchone()
    from app.ai.memo import title_of
    con.execute("INSERT INTO recordings (rec_no, started_at, patient_id, visit_id, state, updated_at, deleted_at, role) "
                "VALUES (99, '2026-11-06T10:00:00', ?, ?, '確定', '2026-11-06T10:00:30', '2026-11-06T10:05:00', 'doctor')", (pid, vid))
    con.execute("INSERT INTO drafts (patient_id, visit_id, kind, body, status, created_at, confirmed_at) "
                "VALUES (?, ?, 'spoken_summary', ?, 'confirmed', '2026-11-06 10:01:00', '2026-11-06T10:02:00')",
                (pid, vid, f"{title_of('done', vday)}: 試しの記録"))
    con.execute("INSERT INTO clinical_notes (patient_id, visit_id, note_date, author_role, body) VALUES (?, ?, ?, 'doctor', ?)",
                (pid, vid, vday, f"{title_of('done', vday)}: 試しの記録"))
    con.commit()
    con.close()
    go(monkeypatch, "2026-11-09")  # 3日後
    con = connect()
    rec = con.execute("SELECT started_at, updated_at, deleted_at FROM recordings WHERE rec_no = 99").fetchone()
    assert rec["started_at"] == "2026-11-09T10:00:00"  # 同じ日数だけ動く
    assert rec["updated_at"] == "2026-11-06T10:00:30" and rec["deleted_at"] == "2026-11-06T10:05:00"  # 待ち時間の時刻は動かない
    new_day = con.execute("SELECT visit_date FROM visits WHERE id = ?", (vid,)).fetchone()[0]
    assert new_day == "2026-11-09" and rec["started_at"][:10] == new_day  # 診療回の日付と日がそろったまま
    d = con.execute("SELECT created_at, confirmed_at, body FROM drafts WHERE body LIKE '%試しの記録%'").fetchone()
    assert d["created_at"] == "2026-11-09 10:01:00" and d["confirmed_at"] == "2026-11-09T10:02:00"
    assert d["body"] == f"{title_of('done', new_day)}: 試しの記録" and "11月6日" not in d["body"]  # 見出しの日付も合う
    note = con.execute("SELECT body FROM clinical_notes WHERE body LIKE '%試しの記録%'").fetchone()[0]
    assert note == f"{title_of('done', new_day)}: 試しの記録"
    seed = con.execute("SELECT started_at, updated_at FROM recordings WHERE rec_no = 1").fetchone()
    assert seed["started_at"][:10] == con.execute("SELECT visit_date FROM visits WHERE id = (SELECT visit_id FROM recordings WHERE rec_no = 1)").fetchone()[0]
    assert seed["updated_at"][:10] == "2026-10-23"  # 見本の録音の updated_at も動かない


# ---------- 5. 印の無い古いデータベース ----------

def test_old_database_without_marker_is_stamped_from_the_sample_row(home, monkeypatch):
    con = connect()
    base_rel = rel(con)
    dates.shift_database(con, 4)  # G21i の頃の作り方: 4日ずらして作ってあった、印の無いデータベース
    con.execute("DELETE FROM app_meta")
    con.commit()
    con.close()
    dates.forget()
    go(monkeypatch, "2026-11-10")  # 作ったときにずらした先と今日が同じ → ずらさず、印だけがつく
    con = connect()
    assert marker(con) == "2026-11-10" and rel(con) == base_rel
    dates.shift_database(con, -2)
    con.execute("DELETE FROM app_meta")
    con.commit()
    con.close()
    dates.forget()
    go(monkeypatch, "2026-11-13")  # 2日前に合わせてあった → 3日進める
    con = connect()
    assert marker(con) == "2026-11-13" and rel(con) == base_rel


def _absolute(con):
    return {(t, c, rid): v for t, cs in dates.SHIFT.items() for c in cs for rid, v in con.execute(f"SELECT id, {c} FROM {t}")}


def test_when_the_sample_row_is_missing_nothing_is_shifted_and_it_is_logged(home, monkeypatch):
    from app.db import initial

    con = connect()
    ref = next(r for r in initial.build()["appointments"] if r["appt_date"] == FIRST)
    con.execute("UPDATE appointments SET start_time = '09:00' WHERE id = ?", (ref["id"],))  # 見本の行が変わっている
    con.execute("DELETE FROM app_meta")
    con.commit()
    con.close()
    dates.forget()
    go(monkeypatch, "2026-11-12")
    before = _absolute(sqlite3.connect(home / "app.db"))
    n = len(errlog.read_recent(50))
    con = connect()
    assert marker(con) == "2026-11-12"  # 今日を印にする
    assert _absolute(con) == before  # 決められないので、ずらさない（間違った日数でずらすより安全）
    assert any("見本の日付" in line for line in errlog.read_recent(50)[n:] or errlog.read_recent(50))  # 黙って流さず、記録に残す


def test_update_adds_missing_sample_rows_at_the_same_alignment(home, monkeypatch):
    go(monkeypatch, "2026-11-09")
    con = connect()
    row = dict(con.execute("SELECT * FROM goods_purchases ORDER BY id LIMIT 1").fetchone())
    con.execute("DELETE FROM goods_purchases WHERE id = ?", (row["id"],))
    con.commit()
    con.close()
    update()  # 足りない行は無ければ足す。すでにずれている分に合わせて入る
    con = connect()
    back = dict(con.execute("SELECT * FROM goods_purchases WHERE id = ?", (row["id"],)).fetchone())
    assert back == row


# ---------- 6. 欄ごとの決まり・固まった日付が残っていないこと ----------

def test_every_date_like_column_is_decided():
    """日付・時刻に見える欄は、ずらすか、ずらさないかを必ず書いてある（新しい欄を足したら、ここで気づく）。"""
    cols = {(t, c[0]) for t, d in schema.TABLES.items() for c in d["cols"]}
    shifted = {(t, c) for t, cs in dates.SHIFT.items() for c in cs}
    assert shifted <= cols and set(dates.KEEP) <= cols and not (shifted & set(dates.KEEP))
    for t, c in sorted(cols):
        if dates.DATEISH.search(c):
            assert (t, c) in shifted or (t, c) in dates.KEEP, f"{t}.{c} をずらすか、ずらさないか決めてください"
    assert all(dates.KEEP[k] for k in dates.KEEP)  # 理由が書いてある


def test_nothing_is_frozen_at_import_time(monkeypatch):
    from app.db import initial
    from app.mockview import parts

    assert not hasattr(initial, "TODAY")
    monkeypatch.setenv("CV_TODAY", "2026-12-24")
    assert "2026年12月24日" in parts.date_text()
    monkeypatch.setenv("CV_TODAY", "2027-01-05")
    assert "2027年1月5日" in parts.date_text()
    assert age_on("1968-05-20", "2026-05-19") == 57 and age_on("1968-05-20") == age_on("1968-05-20", today())
    bad = []
    for p in (ROOT / "app").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        if re.search(r"^(TODAY|DATE)\s*=|import[^\n]*\bTODAY\b|\bapp_today\b\s*=\s*app_today\(\)", text, re.M):
            bad.append(p.name)
    assert not bad, bad


def test_fresh_database_is_aligned_to_today_when_created(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CV_TODAY", "2026-11-20")
    dates.forget()
    update()
    con = connect()
    assert marker(con) == "2026-11-20"
    assert con.execute("SELECT COUNT(*) FROM appointments WHERE appt_date = '2026-11-20' AND status = 'booked'").fetchone()[0] == 6
    assert json.loads(json.dumps(todays(con)))  # 形だけ確かめる


def test_server_start_aligns_before_any_request(home, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    go(monkeypatch, "2026-11-08")  # 前の日に止めていたサーバーを、翌々日に起動した
    with TestClient(app):  # 起動だけ（画面は開かない）
        raw = sqlite3.connect(home / "app.db")
        assert dates.get_marker(raw) == "2026-11-08"
        assert raw.execute("SELECT COUNT(*) FROM appointments WHERE appt_date = '2026-11-08' AND status = 'booked'").fetchone()[0] == 6
