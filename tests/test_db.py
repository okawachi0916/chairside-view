import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATIENTS = ["0123", "0456", "0789", "1024", "2048"]


def run(script, data_dir):
    env = {**os.environ, "CV_DATA_DIR": str(data_dir), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r


def con_of(data_dir):
    con = sqlite3.connect(Path(data_dir) / "app.db")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def counts(con):
    names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {n: con.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0] for n in sorted(names)}


def photos(con):
    return [tuple(r) for r in con.execute("SELECT patient_id, number, taken_on FROM photos ORDER BY id")]


@pytest.fixture()
def seeded(tmp_path):
    run("seed.py", tmp_path)
    return tmp_path


def test_seed_twice_same(tmp_path):
    run("seed.py", tmp_path)
    con = con_of(tmp_path)
    c1, p1 = counts(con), photos(con)
    con.close()
    # 画像は seed で消えない
    (tmp_path / "photos").mkdir()
    (tmp_path / "photos" / "keep.jpg").write_bytes(b"x")
    run("seed.py", tmp_path)
    con = con_of(tmp_path)
    assert counts(con) == c1 and photos(con) == p1
    assert (tmp_path / "photos" / "keep.jpg").exists()
    # 写真番号は患者様の中で重ならない通し番号
    for pid in range(1, 6):
        nums = [n for p, n, _ in p1 if p == pid]
        assert nums == list(range(1, len(nums) + 1))
    # 下書きは花子の今日の2件だけ。確定前なので記録ではない
    assert [tuple(r) for r in con.execute("SELECT patient_id, status FROM drafts")] == [(1, "draft")] * 2
    con.close()


def test_patients_and_today(seeded):
    con = con_of(seeded)
    from app.db import age_on
    ps = con.execute("SELECT * FROM patients ORDER BY id").fetchall()
    assert [p["chart_no"] for p in ps] == PATIENTS
    assert [age_on(p["birth_date"]) for p in ps] == [58, 45, 72, 81, 35]
    assert all(p["name_kana"] for p in ps)
    rows = con.execute("SELECT start_time, end_time, chart_no, name, treatment FROM appointments a "
                       "JOIN patients p ON p.id = a.patient_id WHERE appt_date='2026-11-06' "
                       "ORDER BY start_time, chart_no").fetchall()
    assert [(r[0], r[1], r[2], r[4]) for r in rows] == [
        ("14:30", "15:30", "0123", "RCT"), ("14:30", "15:00", "0456", "SPT"),
        ("14:30", "15:00", "0789", "義歯調整"), ("15:00", "15:30", "1024", "CR"),
        ("15:30", "16:00", "0123", "SPT"), ("15:30", "16:00", "2048", "インレー")]


@pytest.mark.parametrize("pid", range(1, 6))
def test_three_screens_not_empty(seeded, pid):
    con = con_of(seeded)

    def n(sql):
        return con.execute(sql, (pid,)).fetchone()[0]

    # 歯科医師の画面
    for t in ["important_notes", "medical_histories", "handovers", "clinical_notes", "treatment_history",
              "photos", "tooth_status"]:
        assert n(f"SELECT COUNT(*) FROM {t} WHERE patient_id=?") > 0, t
    assert n("SELECT COUNT(*) FROM treatment_plans WHERE patient_id=? AND kind='plan'") > 0
    assert n("SELECT COUNT(*) FROM treatment_plans WHERE patient_id=? AND kind='next'") > 0
    assert n("SELECT COUNT(*) FROM appointments WHERE patient_id=? AND appt_date='2026-11-06'") > 0
    # 歯科衛生士の画面
    for t in ["maintenance_intervals", "care_purchases", "perio_exams"]:
        assert n(f"SELECT COUNT(*) FROM {t} WHERE patient_id=?") > 0, t
    assert n("SELECT COUNT(*) FROM perio_teeth WHERE exam_id IN (SELECT id FROM perio_exams WHERE patient_id=?)") > 0
    # 受付の画面
    for t in ["reception_memos", "goods_purchases", "prescriptions", "visits"]:
        assert n(f"SELECT COUNT(*) FROM {t} WHERE patient_id=?") > 0, t


def test_hanako_matches_mock(seeded):
    con = con_of(seeded)
    q = lambda s, *a: con.execute(s, a).fetchall()
    assert len(q("SELECT 1 FROM clinical_notes WHERE patient_id=1")) == 8
    assert len(q("SELECT 1 FROM treatment_history WHERE patient_id=1")) == 22  # 画面は新しい10行、全画面は遡って全部
    assert len(q("SELECT 1 FROM photos WHERE patient_id=1")) == 17
    assert len(q("SELECT 1 FROM care_purchases WHERE patient_id=1")) == 5
    assert len(q("SELECT 1 FROM goods_purchases WHERE patient_id=1")) == 5
    assert len(q("SELECT 1 FROM prescriptions WHERE patient_id=1")) == 3
    # 去年の CT、インプラント、親知らずの抜歯は入れない
    text = " ".join(str(v) for t in ("treatment_history", "clinical_notes", "tooth_status", "photos")
                    for row in q(f"SELECT * FROM {t} WHERE patient_id=1") for v in tuple(row))
    import re
    assert not re.search(r"(?<![A-Za-z])CT(?![A-Za-z])", text)  # RCT は別
    for w in ("インプラント", "抜歯"):
        assert w not in text
    # 過去1年の来院13回、キャンセル1回 (予約14回)
    assert len(q("SELECT 1 FROM visits WHERE patient_id=1 AND visit_date>='2025-11-06' AND visit_date<'2026-11-06'")) == 13
    assert len(q("SELECT 1 FROM cancellations WHERE patient_id=1")) == 1
    assert len(q("SELECT 1 FROM appointments WHERE patient_id=1 AND status IN ('done','cancelled')")) == 14
    # 曜日と時間帯の数が受付の表と合う
    import datetime as dt
    grid = {}
    for r in q("SELECT visit_date, start_time FROM visits WHERE patient_id=1 AND visit_date<'2026-11-06'"):
        wd = dt.date.fromisoformat(r[0]).weekday()
        band = 0 if r[1] < "12:00" else (1 if r[1] < "17:00" else 2)
        grid[(band, wd)] = grid.get((band, wd), 0) + 1
    assert [[grid.get((b, w), 0) for w in range(6)] for b in range(3)] == [
        [0, 0, 1, 0, 1, 0], [0, 1, 1, 0, 6, 1], [0, 1, 0, 0, 0, 1]]
    # 歯周検査の主な数字
    for date, deep, bop, pcr in [("2026-08-07", 6, 15, 18), ("2026-05-08", 9, 19, 24)]:
        rows = q("SELECT pocket, bop, plaque, mobility FROM perio_teeth t JOIN perio_exams e ON e.id=t.exam_id "
                 "WHERE e.patient_id=1 AND e.exam_date=?", date)
        assert len(rows) == 26
        assert sum(r[0] >= 4 for r in rows) == deep
        assert round(100 * sum(r[1] for r in rows) / 26) == bop
        assert round(100 * sum(r[2].count("1") for r in rows) / (26 * 4)) == pcr
        assert sum(r[3] > 0 for r in rows) == 0
    assert q("SELECT MAX(exam_date) FROM perio_exams WHERE patient_id=1")[0][0] == "2026-08-07"


def test_ichiro_better_and_worse(seeded):
    con = con_of(seeded)

    def deep(d):
        return {r[0] for r in con.execute(
            "SELECT tooth FROM perio_teeth t JOIN perio_exams e ON e.id=t.exam_id "
            "WHERE e.patient_id=2 AND e.exam_date=? AND pocket>=4", (d,))}
    before, after = deep("2026-05-15"), deep("2026-08-14")
    assert len(before) >= 10 and before - after and after - before


def test_notes_and_drafts_need_own_visit(seeded):
    con = con_of(seeded)
    # 患者様 2 の診療回に患者様 1 の診療メモや下書きはつなげない
    visit_of_2 = con.execute("SELECT id FROM visits WHERE patient_id=2").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO clinical_notes (patient_id, visit_id, note_date, body) VALUES (1, ?, '2026-11-06', 'x')",
                    (visit_of_2,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO drafts (patient_id, visit_id, body) VALUES (1, ?, 'x')", (visit_of_2,))
    with pytest.raises(sqlite3.IntegrityError):  # 診療回なしは不可
        con.execute("INSERT INTO drafts (patient_id, body) VALUES (1, 'x')")
    visit_of_1 = con.execute("SELECT id FROM visits WHERE patient_id=1").fetchone()[0]
    con.execute("INSERT INTO drafts (patient_id, visit_id, body) VALUES (1, ?, 'x')", (visit_of_1,))
    con.execute("INSERT INTO voice_fixes (heard) VALUES ('あとで直す')")


def test_update_db_creates_when_missing(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    run("seed.py", a)
    run("update_db.py", b)
    ca, cb = con_of(a), con_of(b)
    assert counts(ca) == counts(cb) and photos(ca) == photos(cb)


def test_update_db_old_database(seeded):
    con = con_of(seeded)
    # 古いデータベース: 列と写真の行が足りない。そこへ新しい診療メモも入っている。
    con.execute("ALTER TABLE photos DROP COLUMN kind")
    con.execute("ALTER TABLE patients DROP COLUMN name_kana")
    con.execute("DROP TABLE voice_fixes")
    con.execute("DELETE FROM photos WHERE patient_id=1 AND number>6")
    con.execute("DELETE FROM important_notes WHERE patient_id=3")
    vid = con.execute("SELECT id FROM visits WHERE patient_id=1 LIMIT 1").fetchone()[0]
    con.execute("INSERT INTO clinical_notes (patient_id, visit_id, note_date, body) VALUES (1, ?, '2026-11-06', '残る')", (vid,))
    con.execute("UPDATE patients SET name='見本 花子' WHERE id=1")
    before = counts(con)
    con.commit()
    con.close()
    run("update_db.py", seeded)
    con = con_of(seeded)
    assert con.execute("SELECT COUNT(*) FROM clinical_notes WHERE body='残る'").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM photos WHERE patient_id=1").fetchone()[0] == 17
    assert con.execute("SELECT COUNT(*) FROM important_notes WHERE patient_id=3").fetchone()[0] == 2
    assert con.execute("SELECT name_kana FROM patients WHERE id=1").fetchone()[0] == "ミホン ハナコ"
    assert con.execute("SELECT kind FROM photos WHERE id=1").fetchone()[0] == "intraoral"
    con.execute("INSERT INTO voice_fixes (heard) VALUES ('x')")
    assert counts(con)["clinical_notes"] == before["clinical_notes"]


def test_update_db_fills_g22_columns_and_rows(seeded):
    """G22 の前のデータベース: 既往のいつから・通院先、受付メモの書いた時期が無く、古い治療歴・検査・治療方針も無い。"""
    con = con_of(seeded)
    for t, c in [("medical_histories", "since"), ("medical_histories", "clinic"), ("reception_memos", "written_on")]:
        con.execute(f"ALTER TABLE {t} DROP COLUMN {c}")
    con.execute("DELETE FROM treatment_plans WHERE kind = 'policy'")
    con.execute("DELETE FROM treatment_history WHERE patient_id=1 AND done_date < '2025-11-14'")
    con.commit()
    con.close()
    run("update_db.py", seeded)
    con = con_of(seeded)
    assert con.execute("SELECT since, clinic FROM medical_histories WHERE patient_id=1 AND seq=1").fetchone()[:] == (
        "2015年", "みどり内科クリニック")
    assert con.execute("SELECT written_on FROM reception_memos WHERE patient_id=1").fetchone()[0] == "2026年9月"
    assert con.execute("SELECT COUNT(*) FROM treatment_plans WHERE kind='policy'").fetchone()[0] == 5
    assert con.execute("SELECT COUNT(*) FROM treatment_history WHERE patient_id=1").fetchone()[0] == 22
