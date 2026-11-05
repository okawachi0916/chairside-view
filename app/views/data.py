"""画面に出すデータをデータベースから読む。毎回読み直し、どこにも保存しない。"""
from datetime import date

from app.ai import segview
from app.db import age_on, connect, db_path
from app.db.update import update
from app.today import today as app_today

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
            (app_today(),))]


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
        "medical": _all(c, "SELECT condition, medication, since, clinic FROM medical_histories WHERE patient_id = ? ORDER BY seq, id", pid),
        "handover": [r["body"] for r in c.execute("SELECT body FROM handovers WHERE patient_id = ? ORDER BY id", (pid,))],
        "memo": [r["body"] for r in c.execute("SELECT body FROM reception_memos WHERE patient_id = ? ORDER BY id", (pid,))],
        "memo_full": _all(c, "SELECT body, written_on FROM reception_memos WHERE patient_id = ? ORDER BY id", pid),
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
            "SELECT body FROM treatment_plans WHERE patient_id = ? AND kind = 'plan' AND superseded_on IS NULL ORDER BY seq, id", (pid,))]
        d["notes"] = _all(c, "SELECT note_date, author_role, body FROM clinical_notes WHERE patient_id = ? "
                             "ORDER BY note_date DESC, id DESC", pid)
        d["history"] = _all(c, "SELECT done_date, site, content FROM treatment_history WHERE patient_id = ? "
                               "ORDER BY done_date DESC, id DESC", pid)
        d["photos"] = [r["number"] for r in c.execute(
            "SELECT number FROM photos WHERE patient_id = ? ORDER BY number", (pid,))]
        d["policy"] = [r["body"] for r in c.execute(
            "SELECT body FROM treatment_plans WHERE patient_id = ? AND kind = 'policy' ORDER BY seq, id", (pid,))]
        d["mucosal"] = _all(c, "SELECT site, name FROM mucosal_conditions WHERE patient_id = ? ORDER BY id", pid)
        d["dentures"] = _all(c, "SELECT site, kind, made_by, made_on FROM dentures WHERE patient_id = ? ORDER BY id", pid)
        # 今日のこの役割の下書きを、新しい順に全部出す（見本データの下書きも録音から作った下書きも同じ扱い）
        d["drafts"] = _all(c, "SELECT d.body, d.transcript FROM drafts d JOIN visits v ON v.id = d.visit_id "
                              "WHERE d.patient_id = ? AND v.visit_date = ? AND v.role = ? ORDER BY d.id DESC", pid, app_today(), role)
        d["summary"] = [x for dr in d["drafts"] for x in dr["body"].split("\n") if x]
        d["transcript"] = "\n".join(dr["transcript"] for dr in d["drafts"] if dr["transcript"])
        vrow = c.execute("SELECT id, visit_date FROM visits WHERE appointment_id = ?", (appt["id"],)).fetchone()
        d["segments"] = segview.list_for_visit(c, vrow["id"] if vrow else None)  # 録音の区切り（録音した順）
        d["seg_today"] = vrow["visit_date"] if vrow else appt["appt_date"]
        d["combined_draft"] = segview.combined_draft(c, vrow["id"] if vrow else None, role)
        d["photo_rows"] = _all(c, "SELECT number, taken_on, file FROM photos WHERE patient_id = ? ORDER BY number", pid)
        d["interval"] = c.execute("SELECT months, last_date FROM maintenance_intervals WHERE patient_id = ?", (pid,)).fetchone()
        d["care"] = _all(c, "SELECT item, last_date FROM care_purchases WHERE patient_id = ? ORDER BY last_date DESC, id", pid)
        d["perio_all"] = _perio(c, pid, None)  # 全画面で過去の検査へ遡る。新しい検査から順
        d["perio"] = d["perio_all"][:2]
        # 歯冠と根があればその2つ、無ければ今までの状態の文字（絵の側で読み替える）
        # 歯冠・根・カリエスの3つ（G07g）。歯冠が空の古い行は今までの1つの状態の文字を読み替える
        d["teeth"] = {r["tooth"]: ((r["crown"], r["root"], bool(r["caries"])) if r["crown"] else r["status"])
                      for r in c.execute("SELECT tooth, status, crown, root, caries FROM tooth_status "
                                         "WHERE patient_id = ?", (pid,))}
    return d


def percent(part, whole):
    """パーセントは四捨五入で整数 (0.5 は切り上げ)。"""
    return int(100 * part / whole + 0.5) if whole else 0


def perio_exam(exam_row, teeth_rows, visit_time=""):
    """検査1回分を画面用の形にする。基本検査も精密検査も同じ形で、精密検査の歯だけ pts（6点のポケット）と bops（6点の出血）を持つ。
    割合: PCR＝赤い面÷（検査した歯×4）。BOP率＝出血のある点÷点の数（基本は歯1本に1点、精密は1本に6点）。"""
    precise = exam_row["kind"] == "precise"
    teeth = {}
    for r in teeth_rows:
        t = dict(r)
        if precise:  # 6点が無い精密検査の歯（壊れたデータ）は、空欄で出す。基本検査の値から作り足さない
            t["pts"] = [int(x) for x in t["pockets6"].split(",")] if t["pockets6"] else [None] * 6
            t["bops"] = [int(x) for x in t["bops6"]] if t["bops6"] else [0] * 6
        teeth[t["tooth"]] = t
    n = len(teeth)
    points = sum(6 if precise else 1 for _ in teeth.values())
    bleeding = sum(sum(t["bops"]) if "bops" in t else t["bop"] for t in teeth.values())
    day = date.fromisoformat(exam_row["exam_date"])
    return {
        "date": exam_row["exam_date"], "weekday": WEEK[day.weekday()], "time": exam_row["exam_time"] or visit_time,
        "kind": exam_row["kind"], "teeth": teeth, "n": n,
        "deep": sum(t["pocket"] >= 4 for t in teeth.values()),
        "bop": percent(bleeding, points),
        "pcr": percent(sum(t["plaque"].count("1") for t in teeth.values()), n * 4),
        "loose": sum(t["mobility"] > 0 for t in teeth.values()),
    }


def _perio(c, pid, limit=2):
    exams = _all(c, "SELECT id, exam_date, kind, exam_time FROM perio_exams WHERE patient_id = ? ORDER BY exam_date DESC, id DESC"
                    + (f" LIMIT {int(limit)}" if limit else ""), pid)
    out = []
    for e in exams:
        rows = _all(c, "SELECT tooth, pocket, bop, plaque, mobility, pockets6, bops6 FROM perio_teeth WHERE exam_id = ?", e["id"])
        v = c.execute("SELECT start_time FROM visits WHERE patient_id = ? AND visit_date = ? ORDER BY id LIMIT 1",
                      (pid, e["exam_date"])).fetchone()
        out.append(perio_exam(e, rows, v[0] if v else ""))
    return out


def reception_data(pid):
    with con() as c:
        d = common(c, pid)
        d["today"] = _all(c, "SELECT * FROM appointments WHERE patient_id = ? AND appt_date = ? AND status = 'booked' "
                             "ORDER BY start_time, id", pid, app_today())
        d["recent"] = _all(c, "SELECT v.visit_date, a.treatment FROM visits v LEFT JOIN appointments a ON a.id = v.appointment_id "
                              "WHERE v.patient_id = ? AND v.visit_date < ? ORDER BY v.visit_date DESC, v.id DESC LIMIT 4",
                           pid, app_today())
        d["visits"] = [r["visit_date"] + " " + r["start_time"] for r in c.execute(
            "SELECT visit_date, start_time FROM visits WHERE patient_id = ? AND visit_date < ? AND visit_date >= ?",
            (pid, app_today(), _year_ago()))]
        d["cancels"] = _all(c, "SELECT cancel_date, no_show, reason FROM cancellations WHERE patient_id = ? "
                               "ORDER BY cancel_date DESC", pid)
        d["appt_count"] = c.execute("SELECT COUNT(*) FROM appointments WHERE patient_id = ? AND status IN ('done','cancelled')",
                                    (pid,)).fetchone()[0]
        d["next"] = c.execute("SELECT body, staff_role, staff_name, minutes, timing FROM treatment_plans "
                              "WHERE patient_id = ? AND kind = 'next' ORDER BY id", (pid,)).fetchone()
        d["booked"] = _all(c, "SELECT appt_date, start_time, role, staff_name, reception_text FROM appointments "
                              "WHERE patient_id = ? AND appt_date > ? AND status = 'booked' ORDER BY appt_date, start_time",
                           pid, app_today())
        d["goods"] = _all(c, "SELECT bought_on, item, qty FROM goods_purchases WHERE patient_id = ? ORDER BY bought_on DESC, id", pid)
        d["rx"] = _all(c, "SELECT prescribed_on, drug, amount FROM prescriptions WHERE patient_id = ? ORDER BY prescribed_on DESC, id", pid)
    return d


def _year_ago():
    t = date.fromisoformat(app_today())
    return t.replace(year=t.year - 1).isoformat()


def reception_patients():
    """受付で選ぶ患者様 (今日の予約がある人)。"""
    with con() as c:
        rows = _all(c, "SELECT p.id, p.chart_no, p.name FROM patients p WHERE p.id IN "
                       "(SELECT patient_id FROM appointments WHERE appt_date = ? AND status = 'booked') "
                       "ORDER BY p.chart_no", app_today())
        for r in rows:
            r["today"] = _all(c, "SELECT start_time, end_time, treatment FROM appointments WHERE patient_id = ? "
                                 "AND appt_date = ? AND status = 'booked' ORDER BY start_time", r["id"], app_today())
        return rows
