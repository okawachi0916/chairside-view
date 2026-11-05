"""清書に渡す、その患者様の情報。今日の予約の処置と部位、治療計画、直近3回の治療歴の要点。
名前は入れない（入っていても、送信口で伏字にしてから送る）。"""


def context_for(con, patient_id, visit_id) -> str:
    if not patient_id:
        return ""
    lines = []
    ap = None
    if visit_id:
        ap = con.execute("SELECT a.treatment, a.detail, a.detail_sub FROM visits v JOIN appointments a ON a.id = v.appointment_id "
                         "WHERE v.id = ?", (visit_id,)).fetchone()
    if ap and (ap["treatment"] or ap["detail"]):
        lines.append("今日の予約の処置: " + " ".join(x for x in (ap["treatment"], ap["detail"], ap["detail_sub"]) if x))
    plans = [r["body"] for r in con.execute(
        "SELECT body FROM treatment_plans WHERE patient_id = ? AND kind = 'plan' AND superseded_on IS NULL ORDER BY seq", (patient_id,))]
    if plans:
        lines.append("治療計画: " + " / ".join(plans))
    hist = [f"{r['done_date']} {r['site']} {r['content']}".strip() for r in con.execute(
        "SELECT done_date, site, content FROM treatment_history WHERE patient_id = ? ORDER BY done_date DESC, id DESC LIMIT 3", (patient_id,))]
    if hist:
        lines.append("直近の治療歴: " + " / ".join(hist))
    return chr(10).join(lines)
