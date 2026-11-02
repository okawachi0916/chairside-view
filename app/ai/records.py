"""この患者様の記録に番号を付ける（患者様の番号×100+1 から）。Claude には番号と本文を渡し、画面に出す本文は同じ番号のデータベースの本文を使う。

治療歴は、同じ日の診療メモがあるものを省く（同じ内容が2つの番号になって、どちらが正解か決まらなくなるため）。
"""
import re
from dataclasses import dataclass, field


@dataclass
class Record:
    number: int
    ref: str            # 試験で正解を指すための印。例: note:2026-10-23
    kind: str           # 画面の見出し
    part: str           # 画面の data-part
    lines: list         # 画面に出す本文（データベースの文字そのまま）
    source: str         # 出どころ（画面の小さい字）
    when: str = ""
    prompt: str = field(default="", repr=False)


def jp_date(iso: str) -> str:
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", iso or "")
    return f"{int(m[1])}年{int(m[2])}月{int(m[3])}日" if m else (iso or "")


def build_records(con, patient_id: int) -> list:
    q = lambda sql: con.execute(sql, (patient_id,)).fetchall()  # noqa: E731
    out = []
    base = patient_id * 100  # 番号は患者様ごとに別の範囲。別の患者様の番号は、この患者様では通らない

    def add(ref, kind, part, lines, source, when=""):
        lines = [x for x in lines if x]
        out.append(Record(base + len(out) + 1, ref, kind, part, lines, source, when,
                          prompt=f"{kind}{'（' + jp_date(when) + '）' if when else ''}: " + " / ".join(lines)))

    for r in q("SELECT seq, body, period, detail FROM important_notes WHERE patient_id=? ORDER BY seq"):
        add(f"important:{r['seq']}", "重要事項", "important", [r["body"], r["period"], r["detail"]], "出どころ: 重要事項")

    med = q("SELECT condition, medication FROM medical_histories WHERE patient_id=? ORDER BY seq")
    if med:
        lines = [m["condition"] + ("、" + m["medication"] if m["medication"] else "") for m in med]
        add("medical", "全身既往・服薬", "medical-history", lines, "出どころ: 全身既往・服薬")

    # 次回の予約 (kind='next') は治療計画の1番目と同じ内容なので、番号を付けない
    for r in q("SELECT seq, body FROM treatment_plans WHERE patient_id=? AND kind='plan' AND superseded_on IS NULL ORDER BY seq"):
        add(f"plan:{r['seq']}", "治療計画", "treatment-plan", [r["body"]], "出どころ: 治療計画")

    note_dates = set()
    for r in q("SELECT note_date, author_role, body FROM clinical_notes WHERE patient_id=? ORDER BY note_date DESC"):
        note_dates.add(r["note_date"])
        who = "歯科衛生士" if r["author_role"] == "hygienist" else "歯科医師"
        add(f"note:{r['note_date']}", f"診療メモ（{who}）", "past-notes", [r["body"]],
            f"出どころ: {jp_date(r['note_date'])}の診療記録", r["note_date"])

    for r in q("SELECT done_date, site, content FROM treatment_history WHERE patient_id=? ORDER BY done_date DESC"):
        if r["done_date"] in note_dates:
            continue
        add(f"history:{r['done_date']}", "治療歴", "treatment-history", [f"{r['site']} {r['content']}"],
            f"出どころ: {jp_date(r['done_date'])}の治療歴", r["done_date"])

    for r in q("SELECT exam_date FROM perio_exams WHERE patient_id=? ORDER BY exam_date DESC"):
        add(f"perio:{r['exam_date']}", "歯周基本検査", "perio-exam", ["歯周基本検査", f"検査日 {jp_date(r['exam_date'])}"],
            f"出どころ: {jp_date(r['exam_date'])}の歯周検査", r["exam_date"])

    for r in q("SELECT body FROM handovers WHERE patient_id=?"):
        add("handover", "申し送り", "", [r["body"]], "出どころ: 申し送り")
    return out
