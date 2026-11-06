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


def _site(tooth: int) -> str:
    return {1: "右上", 2: "左上", 3: "左下", 4: "右下"}[tooth // 10] + f"{tooth % 10}番"


def perio_lines(ex: dict) -> list:
    """検査1回分の数字の行。4mm以上の歯と深さ、出血（BOP）の割合、PCR、動揺のある歯。数字は perio_exam()（歯科衛生士の画面と同じ計算）のもの。"""
    deep = sorted((t, v["pocket"]) for t, v in ex["teeth"].items() if v["pocket"] >= 4)
    loose = sorted(t for t, v in ex["teeth"].items() if v["mobility"] > 0)
    return [
        "4mm以上の歯: " + ("、".join(f"{_site(t)} {p}mm" for t, p in deep) + f"（{len(deep)}本）" if deep else "なし（0本）"),
        f"出血（BOP）: {ex['bop']}%",
        f"PCR: {ex['pcr']}%",
        "動揺のある歯: " + ("、".join(_site(t) for t in loose) + f"（{len(loose)}本）" if loose else "なし（0本）"),
    ]


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

    for r in q("SELECT seq, body FROM treatment_plans WHERE patient_id=? AND kind='plan' AND superseded_on IS NULL ORDER BY seq"):
        add(f"plan:{r['seq']}", "治療計画", "treatment-plan", [r["body"]], "出どころ: 治療計画")
    # G19m: 次回の予定（記録で入る。「次回は？」はここから答える）と、今の治療方針
    nx = [r["body"] for r in q("SELECT body FROM treatment_plans WHERE patient_id=? AND kind='next' AND superseded_on IS NULL ORDER BY id")]
    if nx:
        add("next:1", "次回の予定", "next-appointment", ["、".join(nx)], "出どころ: 次回の予定")
    for i, r in enumerate(q("SELECT body FROM treatment_plans WHERE patient_id=? AND kind='policy' AND superseded_on IS NULL ORDER BY seq, id"), 1):
        add(f"policy:{i}", "治療方針", "", [r["body"]], "出どころ: 治療方針")

    note_dates = set()
    for r in q("SELECT note_date, author_role, body FROM clinical_notes WHERE patient_id=? ORDER BY note_date DESC, id DESC"):
        note_dates.add(r["note_date"])
        who = "歯科衛生士" if r["author_role"] == "hygienist" else "歯科医師"
        add(f"note:{r['note_date']}", f"診療メモ（{who}）", "past-notes", [r["body"]],
            f"出どころ: {jp_date(r['note_date'])}の診療記録", r["note_date"])

    for r in q("SELECT done_date, site, content FROM treatment_history WHERE patient_id=? ORDER BY done_date DESC, id DESC"):
        if r["done_date"] in note_dates:
            continue
        add(f"history:{r['done_date']}", "治療歴", "treatment-history", [f"{r['site']} {r['content']}"],
            f"出どころ: {jp_date(r['done_date'])}の治療歴", r["done_date"])

    from app.views import data as views  # 数字の出し方（割合の計算）は画面と同じ perio_exam() を使う。別に作らない

    newest = views._perio(con, patient_id, 1)
    for r in q("SELECT exam_date FROM perio_exams WHERE patient_id=? ORDER BY exam_date DESC"):
        lines = ["歯周検査", f"検査日 {jp_date(r['exam_date'])}"]
        if newest and newest[0]["date"] == r["exam_date"]:
            lines += perio_lines(newest[0])  # 新しい検査だけ、数字をデータベースのまま渡す
            newest = []
        add(f"perio:{r['exam_date']}", "歯周検査", "perio-exam", lines,
            f"出どころ: {jp_date(r['exam_date'])}の歯周検査", r["exam_date"])

    for r in q("SELECT body FROM handovers WHERE patient_id=?"):
        add("handover", "申し送り", "", [r["body"]], "出どころ: 申し送り")
    return out
