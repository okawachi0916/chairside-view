"""画面に出すデータをデータベースから読む。毎回読み直し、どこにも保存しない。"""
from datetime import date

from app.db import TODAY, age_on, connect, db_path
from app.db.update import update

WEEK = "月火水木金土日"
ROLE_NAME = {"doctor": "歯科医師", "hygienist": "歯科衛生士"}


_ready = set()


def con():
    # 未設定でも起動できるよう、無ければ初期の状態で作る。古ければ足りない分を足す (あるデータは消さない)。
    key = str(db_path())
    if key not in _ready or not db_path().exists():
        update()
        _ready.add(key)
    return connect()


def ja_date(s: str, week=False) -> str:
    d = date.fromisoformat(s)
    out = f"{d.year}年{d.month}月{d.day}日"
    return out + f" {WEEK[d.weekday()]}曜日" if week else out


def slash_date(s: str) -> str:
    d = date.fromisoformat(s)
    return f"{d.year}/{d.month}/{d.day}"


def minutes(start: str, end: str) -> int:
    h1, m1 = map(int, start.split(":"))
    h2, m2 = map(int, end.split(":"))
    return (h2 * 60 + m2) - (h1 * 60 + m1)


def duration(n: int) -> str:
    h, m = divmod(n, 60)
    if h and m:
        return f"{h}時間{m}分"
    return f"{h}時間" if h else f"{m}分"


def today_list():
    """今日の予約 (予約一覧の行)。"""
    with con() as c:
        return [dict(r) for r in c.execute(
            "SELECT a.id, a.start_time, a.end_time, a.treatment, a.role, p.id AS patient_id, "
            "p.chart_no, p.name FROM appointments a JOIN patients p ON p.id = a.patient_id "
            "WHERE a.appt_date = ? AND a.status = 'booked' ORDER BY a.start_time, p.chart_no, a.id",
            (TODAY,))]


def appointment(appt_id: int):
    with con() as c:
        r = c.execute("SELECT * FROM appointments WHERE id = ?", (appt_id,)).fetchone()
        return dict(r) if r else None


def patient_head(c, pid):
    p = dict(c.execute("SELECT * FROM patients WHERE id = ?", (pid,)).fetchone())
    p["age"] = age_on(p["birth_date"])
    return p


def _all(c, sql, *args):
    return [dict(r) for r in c.execute(sql, args)]


def common(c, pid):
    """歯科医師・歯科衛生士・受付で共通に出す物。"""
    return {
        "patient": patient_head(c, pid),
        "important": [r["body"] for r in c.execute(
            "SELECT body FROM important_notes WHERE patient_id = ? ORDER BY seq, id", (pid,))],
        "important_full": _all(c, "SELECT body, period, detail FROM important_notes WHERE patient_id = ? ORDER BY seq, id", pid),
        "medical": _all(c, "SELECT condition, medication FROM medical_histories WHERE patient_id = ? ORDER BY seq, id", pid),
        "handover": [r["body"] for r in c.execute("SELECT body FROM handovers WHERE patient_id = ? ORDER BY id", (pid,))],
        "memo": [r["body"] for r in c.execute("SELECT body FROM reception_memos WHERE patient_id = ? ORDER BY id", (pid,))],
    }


def same_day(c, appt):
    return _all(c, "SELECT * FROM appointments WHERE patient_id = ? AND appt_date = ? AND status = 'booked' "
                   "ORDER BY start_time, id", appt["patient_id"], appt["appt_date"])


def unit_data(appt, role):
    pid = appt["patient_id"]
    with con() as c:
        d = common(c, pid)
        d["appt"], d["role"] = appt, role
        d["day"] = same_day(c, appt)
        d["plan"] = [r["body"] for r in c.execute(
            "SELECT body FROM treatment_plans WHERE patient_id = ? AND kind = 'plan' ORDER BY seq, id", (pid,))]
        d["notes"] = _all(c, "SELECT note_date, author_role, body FROM clinical_notes WHERE patient_id = ? "
                             "ORDER BY note_date DESC, id DESC", pid)
        d["history"] = _all(c, "SELECT done_date, site, content FROM treatment_history WHERE patient_id = ? "
                               "ORDER BY done_date DESC, id DESC", pid)
        d["photos"] = [r["number"] for r in c.execute(
            "SELECT number FROM photos WHERE patient_id = ? ORDER BY number", (pid,))]
        d["mucosal"] = _all(c, "SELECT site, name FROM mucosal_conditions WHERE patient_id = ? ORDER BY id", pid)
        d["dentures"] = _all(c, "SELECT site, kind, made_by, made_on FROM dentures WHERE patient_id = ? ORDER BY id", pid)
        d["drafts"] = _all(c, "SELECT d.body, d.transcript FROM drafts d JOIN visits v ON v.id = d.visit_id "
                              "WHERE d.patient_id = ? AND v.visit_date = ? AND v.role = ? ORDER BY d.id", pid, TODAY, role)
        d["summary"] = [x for dr in d["drafts"] for x in dr["body"].split("\n") if x]
        d["transcript"] = "\n".join(dr["transcript"] for dr in d["drafts"] if dr["transcript"])
        d["photo_rows"] = _all(c, "SELECT number, taken_on FROM photos WHERE patient_id = ? ORDER BY number", pid)
        d["interval"] = c.execute("SELECT months, last_date FROM maintenance_intervals WHERE patient_id = ?", (pid,)).fetchone()
        d["care"] = _all(c, "SELECT item, last_date FROM care_purchases WHERE patient_id = ? ORDER BY last_date DESC, id", pid)
        d["perio"] = _perio(c, pid)
    return d


def _perio(c, pid):
    exams = _all(c, "SELECT id, exam_date FROM perio_exams WHERE patient_id = ? ORDER BY exam_date DESC LIMIT 2", pid)
    out = []
    for e in exams:
        teeth = {r["tooth"]: dict(r) for r in c.execute(
            "SELECT tooth, pocket, bop, plaque, mobility FROM perio_teeth WHERE exam_id = ?", (e["id"],))}
        n = len(teeth) or 1
        out.append({
            "date": e["exam_date"], "teeth": teeth, "n": len(teeth),
            "deep": sum(t["pocket"] >= 4 for t in teeth.values()),
            "bop": round(100 * sum(t["bop"] for t in teeth.values()) / n),
            "pcr": round(100 * sum(t["plaque"].count("1") for t in teeth.values()) / (n * 4)),
            "loose": sum(t["mobility"] > 0 for t in teeth.values()),
        })
    return out


def reception_data(pid):
    with con() as c:
        d = common(c, pid)
        d["today"] = _all(c, "SELECT * FROM appointments WHERE patient_id = ? AND appt_date = ? AND status = 'booked' "
                             "ORDER BY start_time, id", pid, TODAY)
        d["recent"] = _all(c, "SELECT v.visit_date, a.treatment FROM visits v LEFT JOIN appointments a ON a.id = v.appointment_id "
                              "WHERE v.patient_id = ? AND v.visit_date < ? ORDER BY v.visit_date DESC, v.id DESC LIMIT 4",
                           pid, TODAY)
        d["visits"] = [r["visit_date"] + " " + r["start_time"] for r in c.execute(
            "SELECT visit_date, start_time FROM visits WHERE patient_id = ? AND visit_date < ? AND visit_date >= ?",
            (pid, TODAY, _year_ago()))]
        d["cancels"] = _all(c, "SELECT cancel_date, no_show, reason FROM cancellations WHERE patient_id = ? "
                               "ORDER BY cancel_date DESC", pid)
        d["appt_count"] = c.execute("SELECT COUNT(*) FROM appointments WHERE patient_id = ? AND status IN ('done','cancelled')",
                                    (pid,)).fetchone()[0]
        d["next"] = c.execute("SELECT body, staff_role, staff_name, minutes, timing FROM treatment_plans "
                              "WHERE patient_id = ? AND kind = 'next' ORDER BY id", (pid,)).fetchone()
        d["booked"] = _all(c, "SELECT appt_date, start_time, role, staff_name, reception_text FROM appointments "
                              "WHERE patient_id = ? AND appt_date > ? AND status = 'booked' ORDER BY appt_date, start_time",
                           pid, TODAY)
        d["goods"] = _all(c, "SELECT bought_on, item, qty FROM goods_purchases WHERE patient_id = ? ORDER BY bought_on DESC, id", pid)
        d["rx"] = _all(c, "SELECT prescribed_on, drug, amount FROM prescriptions WHERE patient_id = ? ORDER BY prescribed_on DESC, id", pid)
    return d


def _year_ago():
    t = date.fromisoformat(TODAY)
    return t.replace(year=t.year - 1).isoformat()


def reception_patients():
    """受付で選ぶ患者様 (今日の予約がある人)。"""
    with con() as c:
        rows = _all(c, "SELECT p.id, p.chart_no, p.name FROM patients p WHERE p.id IN "
                       "(SELECT patient_id FROM appointments WHERE appt_date = ? AND status = 'booked') "
                       "ORDER BY p.chart_no", TODAY)
        for r in rows:
            r["today"] = _all(c, "SELECT start_time, end_time, treatment FROM appointments WHERE patient_id = ? "
                                 "AND appt_date = ? AND status = 'booked' ORDER BY start_time", r["id"], TODAY)
        return rows
