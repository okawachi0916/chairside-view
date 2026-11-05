"""見本の日付を、開いた日の「今日」へ合わせる決まり。ずらす欄・ずらさない欄・ずらし方は、この1か所だけにある。

- データベースに「見本の BASE の日を、何日に合わせたか」の印を1つ持つ（app_meta の dates_aligned_to）。
- 印の日と今日の差の日数だけ、画面に「何日」と出る日付をまとめてずらし、印を今日にする。差が0なら何もしない。
  日付を戻したとき（差がマイナス）も同じ決まりで合う。
- どの欄をずらすかは、欄ごとに決めてある（SHIFT と KEEP）。「日付の形の文字だから」では決めない。
- 通す場所: データベースを開くとき（app/db/__init__.py の connect。サーバーの起動後の最初の読み込み、日付をまたいだあとの次の読み込み）、
  見本を作る・足すとき（app/db/update.py。scripts/demo_state.py restore も最後に update を動かす）。
"""
import re
from pathlib import Path
import sqlite3
from datetime import date, timedelta

from app import errlog
from app.today import BASE, today

META = "app_meta"
KEY = "dates_aligned_to"

# ずらす欄: 画面に「何日」と出る日付。形は YYYY-MM-DD か、日付で始まる日時（2026-11-06 14:50、2026-11-06T14:50:03）。時刻の部分はそのまま。
SHIFT = {
    "appointments": ["appt_date"],
    "visits": ["visit_date"],
    "clinical_notes": ["note_date"],
    "treatment_history": ["done_date"],
    "photos": ["taken_on"],
    "treatment_plans": ["superseded_on"],
    "tooth_status_history": ["superseded_on"],  # G19l: 変わる前の歯の状態を残した日（診療回の日）。診療メモ・治療歴の日付と同じだけ動く
    "dentures": ["made_on"],
    "perio_exams": ["exam_date"],
    "maintenance_intervals": ["last_date"],
    "care_purchases": ["last_date"],
    "goods_purchases": ["bought_on"],
    "prescriptions": ["prescribed_on"],
    "cancellations": ["cancel_date"],
    "drafts": ["created_at", "confirmed_at"],  # 院長が試しに入れた要約も、見本と同じだけずらす（間隔を保つ）
    "recordings": ["started_at"],  # 院長が試しに入れた録音も同じ。診療回の日付（visits.visit_date）と日がそろっていることを、読む側が使う
}

# ずらさない欄と、その理由。日付・時刻に見える欄は、必ずここか SHIFT のどちらかに書く（試験が確かめる）。
KEEP = {
    ("patients", "birth_date"): "ずらすと年齢が変わるため",
    ("appointments", "start_time"): "時刻だけで日付を持たない",
    ("appointments", "end_time"): "時刻だけで日付を持たない",
    ("visits", "start_time"): "時刻だけで日付を持たない",
    ("perio_exams", "exam_time"): "時刻だけで日付を持たない",
    ("medical_histories", "since"): "「2015年」のように年だけの文字（いつから病気か。見本の日付ではない）",
    ("important_notes", "period"): "「2018年」のように年だけの文字",
    ("reception_memos", "written_on"): "「2026年9月」のように年月だけの文字",
    ("treatment_plans", "timing"): "「2週間後ごろ」のような言葉で、日付ではない",
    ("recordings", "updated_at"): "機械が待ち時間（止まったままの判定）を測る時刻。ずらすと「何秒前」が狂う",
    ("recordings", "deleted_at"): "削除してから元に戻せる時間を測る時刻。ずらすと「何秒前」が狂う",
    ("phone_links", "created_at"): "QR の有効期限を測る秒の数",
    ("phone_links", "expires_at"): "QR の有効期限を測る秒の数",
    ("phone_events", "at"): "スマホの写真の合図を、時刻の順に拾うための時刻",
    ("voice_fixes", "created_at"): "聞き違いの記録の時刻（機械の記録）",
}

# 日付・時刻に見える欄の名前（SHIFT か KEEP に書いてあるかを確かめる試験が使う）
DATEISH = re.compile(r"(date|_on$|_at$|^at$|^since$|^period$|^timing$|_time$)")

_HEAD = re.compile(r"^(\d{4}-\d{2}-\d{2})(?!\d)(.*)$", re.S)
_checked: dict = {}  # データベースの場所 → 最後に今日へ合わせた日（同じ日の2回目からは調べない）


def shift_text(v, days: int):
    """日付で始まる文字だけを、days 日ずらす。欄が日付の欄かどうかは、呼ぶ側（SHIFT）が決める。"""
    if not isinstance(v, str):
        return v
    m = _HEAD.match(v)
    if not m:
        return v
    try:
        return (date.fromisoformat(m.group(1)) + timedelta(days=days)).isoformat() + m.group(2)
    except ValueError:
        return v


def shift_rows(data: dict, days: int):
    """見本の行（initial.build() の結果）を、SHIFT の欄だけずらす。すでにずらしてあるデータベースへ足す行をそろえるのに使う。"""
    if days:
        for table, cols in SHIFT.items():
            for row in data.get(table, []):
                for c in cols:
                    if c in row:
                        row[c] = shift_text(row[c], days)
    return data


def _has(con, table: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def get_marker(con):
    if not _has(con, META):
        return None
    r = con.execute(f"SELECT value FROM {META} WHERE key = ?", (KEY,)).fetchone()
    return r[0] if r else None


def set_marker(con, day: str):
    con.execute(f"INSERT INTO {META} (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (KEY, day))


def detect(con) -> str:
    """印の無いデータベースの印を決める。見本は毎回同じ中身で作られるので、見本の決まった1行
    （見本の「今日」の最初の予約。番号も患者様も時刻も見本で決まっている）の今の日付が、BASE をずらした先の日。
    行が無い（空のデータベース）なら BASE。見本の行が見つからない・違うときは、ずらさない（今日を印にして、記録に残す）。"""
    from app.db import initial  # 循環を避けるため、使うときに読む

    if not _has(con, "appointments") or con.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == 0:
        return BASE
    ref = next(r for r in initial.build()["appointments"] if r["appt_date"] == BASE)
    row = con.execute("SELECT appt_date, patient_id, start_time, role FROM appointments WHERE id = ?", (ref["id"],)).fetchone()
    if row and (row[1], row[2], row[3]) == (ref["patient_id"], ref["start_time"], ref["role"]) and _HEAD.match(row[0] or ""):
        return row[0][:10]
    errlog.record("見本の日付", "印の無いデータベースで、見本の基準の行が見つからず、ずらしませんでした")
    return today()


def shift_database(con, days: int):
    """SHIFT の欄を days 日ずらす。同じ日の検査を1人に2つ持てない決まり（perio_exams）に途中で当たらないよう、動く向きの先の行から順に直す。
    診療メモの見出しに入っている診療回の日付（memo.title_of）も、同じだけ直す。"""
    from app.ai.memo import title_of

    old_day = {r[0]: r[1] for r in con.execute("SELECT id, visit_date FROM visits")}
    order = "DESC" if days > 0 else "ASC"
    for table, cols in SHIFT.items():
        for col in cols:
            rows = con.execute(f"SELECT id, {col} FROM {table} WHERE {col} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*' "
                               f"ORDER BY {col} {order}, id").fetchall()
            for rid, v in rows:
                con.execute(f"UPDATE {table} SET {col} = ? WHERE id = ?", (shift_text(v, days), rid))
    new_day = {r[0]: r[1] for r in con.execute("SELECT id, visit_date FROM visits")}
    for table in ("clinical_notes", "drafts"):
        for rid, vid, body in con.execute(f"SELECT id, visit_id, body FROM {table} WHERE visit_id IS NOT NULL").fetchall():
            if vid in old_day and old_day[vid] != new_day.get(vid):
                a, b = title_of("done", old_day[vid]), title_of("done", new_day[vid])
                if body and a in body:
                    con.execute(f"UPDATE {table} SET body = ? WHERE id = ?", (body.replace(a, b), rid))


def align(con, to=None) -> int:
    """印の日と「今日」の差の日数だけ日付をずらし、印を今日にする。ずらした日数を返す（0なら何もしていない）。
    2つの道（サーバーと restore など）が同時に動いても二重にずれないよう、印は書き込みの鍵を取ってから読み直す。"""
    to = to or today()
    if not _has(con, META):
        return 0
    if con.in_transaction:
        con.commit()
    con.execute("BEGIN IMMEDIATE")
    try:
        cur = get_marker(con)
        if cur is None:
            cur = detect(con)
        days = (date.fromisoformat(to) - date.fromisoformat(cur)).days
        if days:
            shift_database(con, days)
        if cur != to or get_marker(con) is None:
            set_marker(con, to)
        con.commit()
        return days
    except Exception:
        con.rollback()
        raise


def ensure(con, path) -> int:
    """データベースを開くたびに通す入口。同じ日の2回目からは何もしない（サーバーが夜をまたいだら、次の読み込みで1回だけ動く）。"""
    key, t = str(path), today()
    if _checked.get(key) == t:
        return 0
    if not _has(con, META):  # まだ表が無い（update() が作る前）。印がつくまで、次に開くときも調べる
        return 0
    n = align(con, t)
    _checked[key] = t
    return n


def mark_checked(path):
    """update() が今日へ合わせ終えたデータベースを、「合わせ済み」と覚える。"""
    _checked[str(Path(path))] = today()


def forget(path=None):
    """覚えている「今日へ合わせた」を忘れる（データベースを入れ替えた・試験で日付を動かしたとき）。"""
    if path is None:
        _checked.clear()
    else:
        _checked.pop(str(path), None)
