"""架空の患者様5人の初期データ。番号は毎回同じになるよう、書いた順に1から振る。"""
from datetime import date

TODAY = "2026-11-06"  # 今日の日付は固定

UPPER = list(range(18, 10, -1)) + list(range(21, 29))
LOWER = list(range(48, 40, -1)) + list(range(31, 39))
ALL_TEETH = UPPER + LOWER


def age_on(birth_date: str, today: str = TODAY) -> int:
    b, t = date.fromisoformat(birth_date), date.fromisoformat(today)
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


class _Rows(dict):
    """表ごとの行の一覧。id は表ごとに書いた順に 1 から振る。"""

    def add(self, table, **row):
        rows = self.setdefault(table, [])
        row = {"id": len(rows) + 1, **row}
        rows.append(row)
        return row["id"]


def _perio(rows, pid, exam_date, teeth, deep, bop, plaque):
    """基本検査。deep=4mm以上の歯、bop=出血のある歯、plaque=付着が1か所ある歯 (歯番の集合)。"""
    eid = rows.add("perio_exams", patient_id=pid, exam_date=exam_date)
    for i, t in enumerate(teeth):
        pocket = 2 + (i % 2)
        if t in deep:
            pocket = 4 + (t % 3 == 0)
        flags = ["0"] * 4
        if t in plaque:
            flags[t % 4] = "1"
        rows.add("perio_teeth", exam_id=eid, tooth=t, pocket=pocket,
                 bop=int(t in bop), plaque="".join(flags), mobility=0)


def build() -> dict:
    r = _Rows()

    # ---- 患者様 ----
    pats = [
        ("0123", "見本 花子", "ミホン ハナコ", "1968-05-20", "女性"),
        ("0456", "見本 一郎", "ミホン イチロウ", "1981-03-14", "男性"),
        ("0789", "見本 太郎", "ミホン タロウ", "1954-01-09", "男性"),
        ("1024", "見本 和子", "ミホン カズコ", "1945-06-30", "女性"),
        ("2048", "見本 美咲", "ミホン ミサキ", "1991-09-02", "女性"),
    ]
    for chart_no, name, kana, birth, sex in pats:
        r.add("patients", chart_no=chart_no, name=name, name_kana=kana, birth_date=birth, sex=sex)
    H, I, T, K, M = 1, 2, 3, 4, 5

    # ---- 予約と診療回 ----
    def appt(pid, d, s, e, role, treat, unit, status="done", detail="", sub="", recep="", staff=""):
        return r.add("appointments", patient_id=pid, appt_date=d, start_time=s, end_time=e, role=role,
                     treatment=treat, unit=unit, status=status, detail=detail, detail_sub=sub,
                     reception_text=recep, staff_name=staff)

    def visit(pid, d, s, role, treat, unit):
        a = appt(pid, d, s, "", role, treat, unit)
        return r.add("visits", patient_id=pid, appointment_id=a, visit_date=d, start_time=s,
                     role=role, unit=unit)

    # 花子の過去13回。曜日と時間帯の数が受付の表 (金曜の午後6回など) と合うようにしてある。
    hv = {}
    for d, s, role, treat in [
        ("2025-11-25", "17:30", "hygienist", "SPT"),
        ("2025-12-17", "10:00", "doctor", "CR"),
        ("2026-01-09", "11:00", "doctor", "支台築造"),
        ("2026-02-06", "14:30", "hygienist", "SPT"),
        ("2026-03-28", "17:30", "doctor", "クラウン装着"),
        ("2026-04-14", "14:30", "doctor", "知覚過敏処置"),
        ("2026-05-08", "14:30", "hygienist", "SPT"),
        ("2026-06-20", "14:30", "doctor", "診察"),
        ("2026-07-15", "14:30", "doctor", "CR"),
        ("2026-08-07", "14:30", "hygienist", "SPT"),
        ("2026-09-18", "14:30", "doctor", "RCT"),
        ("2026-10-09", "14:30", "doctor", "RCT"),
        ("2026-10-23", "14:30", "doctor", "RCT"),
    ]:
        hv[d] = visit(H, d, s, role, treat, 2)
    # 当日キャンセルが1回 (予約は全部で14回)
    ca = appt(H, "2026-03-12", "14:30", "15:00", "doctor", "診察", 2, status="cancelled")
    r.add("cancellations", patient_id=H, appointment_id=ca, cancel_date="2026-03-12",
          no_show=0, reason="当日の朝に電話あり")

    ov = {}  # 他の4人の過去3回
    for pid, role, treat, ds in [
        (I, "hygienist", "SPT", ["2026-02-13", "2026-05-15", "2026-08-14"]),
        (T, "doctor", "義歯調整", ["2026-07-03", "2026-09-04", "2026-10-16"]),
        (K, "doctor", "CR", ["2026-08-21", "2026-09-25", "2026-10-30"]),
        (M, "doctor", "インレー", ["2026-07-24", "2026-09-11", "2026-10-02"]),
    ]:
        for d in ds:
            ov[(pid, d)] = visit(pid, d, "14:30", role, treat, 1)
    for pid, d, reason in [(T, "2026-06-05", "体調不良の連絡あり"), (M, "2026-04-03", "お子さんの発熱")]:
        ca = appt(pid, d, "14:30", "15:00", "doctor", "診察", 1, status="cancelled")
        r.add("cancellations", patient_id=pid, appointment_id=ca, cancel_date=d, no_show=0, reason=reason)

    # 今日の予約 (予約一覧の6行)
    today_h_doc = appt(H, TODAY, "14:30", "15:30", "doctor", "RCT", 2, status="booked", detail="右下6番 根管充填",
                       sub="根管治療 3回目", recep="右下第一大臼歯 RCT", staff="大川内")
    appt(I, TODAY, "14:30", "15:00", "hygienist", "SPT", 1, status="booked", recep="SPT", staff="佐藤")
    appt(T, TODAY, "14:30", "15:00", "doctor", "義歯調整", 3, status="booked", recep="義歯調整", staff="大川内")
    appt(K, TODAY, "15:00", "15:30", "doctor", "CR", 3, status="booked", recep="CR", staff="大川内")
    today_h_hyg = appt(H, TODAY, "15:30", "16:00", "hygienist", "SPT", 2, status="booked", recep="SPT＋TBI",
                       staff="佐藤")
    appt(M, TODAY, "15:30", "16:00", "doctor", "インレー", 3, status="booked", recep="インレー", staff="大川内")
    # 花子の今日の診療回 (診察を始めると作られる) と、話した内容の下書き。下書きは確定するまで記録ではない。
    tv_doc = r.add("visits", patient_id=H, appointment_id=today_h_doc, visit_date=TODAY, start_time="14:30",
                   role="doctor", unit=2, status="open")
    tv_hyg = r.add("visits", patient_id=H, appointment_id=today_h_hyg, visit_date=TODAY, start_time="15:30",
                   role="hygienist", unit=2, status="open")
    r.add("drafts", patient_id=H, visit_id=tv_doc, kind="spoken_summary", status="draft",
          body="右下6番 根管充填、側方加圧\nデンタルで確認、問題なし\n次回 支台築造と形成、2週間後ごろ",
          transcript="右下6番、根管充填をします。側方加圧で詰めました。デンタルで確認して、問題ありませんでした。"
                     "次回は支台築造と形成です。二週間後ごろでお願いします。",
          created_at=TODAY + " 14:50")
    r.add("drafts", patient_id=H, visit_id=tv_hyg, kind="spoken_summary", status="draft",
          body="右下奥の清掃を指導\n寝る前の歯間ブラシを継続",
          transcript="右下の奥は磨き残しが出やすいので、清掃の仕方をお伝えしました。寝る前の歯間ブラシは続けてください。",
          created_at=TODAY + " 15:40")
    # 予約済みの次の予約
    appt(H, "2027-02-05", "14:30", "15:00", "hygienist", "SPT", 2, status="booked",
         recep="3か月SPT", staff="佐藤")

    # ---- 重要事項・全身既往と服薬・申し送り・受付メモ ----
    for pid, items in {
        H: [("ペニシリン系抗菌薬アレルギー", "2019年", "全身の発疹。アモキシシリン服用後"),
            ("ビスホスホネート製剤服用中", "2021年", "骨粗鬆症の治療で開始")],
        I: [("金属アレルギー（ニッケル）", "2015年", "装飾品で皮膚炎")],
        T: [("ワルファリン服用中", "2020年", "心房細動の治療で開始")],
        K: [("関節リウマチ 手に力が入りにくい", "2012年", "診断を受けた")],
        M: [("ラテックスアレルギー", "2018年", "手袋で手がかゆくなった")],
    }.items():
        for i, (b, period, detail) in enumerate(items, 1):
            r.add("important_notes", patient_id=pid, seq=i, body=b, period=period, detail=detail)
    for pid, items in {
        H: [("高血圧", "アムロジピン内服中", "2015年", "みどり内科クリニック"),
            ("脂質異常症", "ロスバスタチン内服中", "2017年", "みどり内科クリニック"),
            ("骨粗鬆症", "BP製剤内服中", "2021年", "ひかり整形外科"),
            ("ペニシリン系抗菌薬アレルギー", "", "2019年", "")],
        I: [("2型糖尿病", "メトホルミン内服中", "2018年", "さくら内科")],
        T: [("心房細動", "ワルファリン内服中", "2020年", "中央総合病院 循環器内科"),
            ("高血圧", "アジルサルタン内服中", "2012年", "中央総合病院 循環器内科")],
        K: [("高血圧", "カンデサルタン内服中", "2005年", "あおば医院"),
            ("2型糖尿病", "シタグリプチン内服中", "2010年", "あおば医院"),
            ("慢性心不全", "ビソプロロール内服中", "2019年", "中央総合病院 循環器内科"),
            ("逆流性食道炎", "ランソプラゾール内服中", "2020年", "あおば医院"),
            ("関節リウマチ", "メトトレキサート内服中", "2012年", "ひかり整形外科")],
        M: [("鉄欠乏性貧血", "鉄剤内服中", "2025年", "さくら内科")],
    }.items():
        for i, (c, m, since, clinic) in enumerate(items, 1):
            r.add("medical_histories", patient_id=pid, seq=i, condition=c, medication=m, since=since, clinic=clinic)
    for pid, b in [
        (H, "長く口を開けているのがつらい方です"),
        (I, "音の大きい器具が苦手な方です"),
        (T, "口角にワセリンを塗ってください"),
        (K, "義歯を外すときは声をかけてください"),
        (M, "お子さん用の椅子を用意してください"),
    ]:
        r.add("handovers", patient_id=pid, body=b)
    for pid, b, on in [
        (H, "お子さん3人と同じ時間で予約を取る", "2026年9月"),
        (I, "会計はカード希望", "2026年8月"),
        (T, "送迎のご家族が待合室で待つ", "2026年7月"),
        (K, "車いすのため入口のスロープを使う", "2026年10月"),
        (M, "駐車場を1台確保する", "2026年10月"),
    ]:
        r.add("reception_memos", patient_id=pid, body=b, written_on=on)

    # ---- 治療計画・次回の予定 ----
    for pid, plan, nxt in [
        (H, ["右下6番 次回 支台築造と形成、そのあとクラウン", "左下7番 3か月様子を見る", "その間に 右上5番 の充填"],
         ("支台築造＋形成印象", "doctor", "大川内", 60, "2週間後ごろ")),
        (I, ["全顎の歯周管理を3か月ごとに続ける", "左上6番 経過観察"],
         ("SPT", "hygienist", "佐藤", 30, "3か月後")),
        (T, ["下顎ブリッジ 来月再調整", "上顎左側ブリッジ 経過観察"],
         ("義歯調整", "doctor", "大川内", 30, "4週間後ごろ")),
        (K, ["上顎義歯 来月調整", "下顎義歯 経過観察"],
         ("義歯調整", "doctor", "大川内", 30, "1か月後")),
        (M, ["右上6番 インレー装着", "左下5番 経過観察"],
         ("インレー装着", "doctor", "大川内", 30, "1週間後")),
    ]:
        for i, b in enumerate(plan, 1):
            r.add("treatment_plans", patient_id=pid, seq=i, kind="plan", body=b)
        body, role, name, minutes, timing = nxt
        r.add("treatment_plans", patient_id=pid, seq=0, kind="next", body=body, staff_role=role,
              staff_name=name, minutes=minutes, timing=timing)

    # ---- 診療メモ (診療回に必ずつなぐ) ----
    for d, role, body in [
        ("2026-10-23", "doctor", "右下6番 根管貼薬、仮封、打診痛なし。症状がなければ次回根管充填"),
        ("2026-10-09", "doctor", "右下6番 抜髄、貼薬。次回は症状を確かめて貼薬交換"),
        ("2026-09-18", "doctor", "右下6番 C3と診断、デンタル撮影。次回抜髄"),
        ("2026-08-07", "hygienist", "SPT、歯周検査"),
        ("2026-07-15", "doctor", "左下7番 コンポジットレジン充填"),
        ("2026-06-20", "doctor", "左下7番 C2と診断。次回充填"),
        ("2026-05-08", "hygienist", "SPT"),
        ("2026-04-14", "doctor", "右上5番 知覚過敏の処置"),
    ]:
        r.add("clinical_notes", patient_id=H, visit_id=hv[d], note_date=d, author_role=role, body=body)
    for pid, d, role, body in [
        (I, "2026-08-14", "hygienist", "SPT、歯周検査"),
        (I, "2026-05-15", "hygienist", "SPT、歯周検査"),
        (T, "2026-10-16", "doctor", "下顎ブリッジ 咬合調整"),
        (T, "2026-09-04", "doctor", "下顎ブリッジ 床下粘膜の確認"),
        (K, "2026-10-30", "doctor", "下顎義歯 疼痛部位の調整"),
        (K, "2026-09-25", "doctor", "上顎義歯 適合の確認"),
        (M, "2026-10-02", "doctor", "右上6番 インレー形成、印象"),
        (M, "2026-09-11", "doctor", "右上6番 C2と診断。次回形成"),
    ]:
        r.add("clinical_notes", patient_id=pid, visit_id=ov[(pid, d)], note_date=d, author_role=role, body=body)

    # ---- 治療歴 ----
    for d, site, c in [
        ("2026-10-23", "右下6番", "根管貼薬、仮封"),
        ("2026-10-09", "右下6番", "抜髄、貼薬"),
        ("2026-09-18", "右下6番", "デンタル撮影"),
        ("2026-08-07", "全顎", "SPT、歯周検査"),
        ("2026-07-15", "左下7番", "CR充填"),
        ("2026-06-20", "左下7番", "C2の診断"),
        ("2026-05-08", "全顎", "SPT、義歯の作成"),
        ("2026-04-14", "右上5番", "知覚過敏の処置"),
        ("2026-02-06", "全顎", "SPT、歯周検査"),
        ("2025-11-14", "右上6番", "クラウン装着"),
    ]:
        r.add("treatment_history", patient_id=H, done_date=d, site=site, content=c)
    for pid, rows_ in {
        I: [("2026-08-14", "全顎", "SPT"), ("2026-05-15", "全顎", "SPT"), ("2026-02-13", "全顎", "SPT")],
        T: [("2026-10-16", "下顎", "ブリッジ 咬合調整"), ("2026-09-04", "下顎", "ブリッジ 床下粘膜の確認"),
            ("2026-07-03", "上顎左側", "ブリッジ 調整")],
        K: [("2026-10-30", "下顎", "義歯 疼痛部位の調整"), ("2026-09-25", "上顎", "義歯 適合の確認"),
            ("2026-08-21", "右下5番", "コンポジットレジン充填")],
        M: [("2026-10-02", "右上6番", "インレー形成・印象"), ("2026-09-11", "右上6番", "C2の診断"),
            ("2026-07-24", "全顎", "スケーリング")],
    }.items():
        for d, site, c in rows_:
            r.add("treatment_history", patient_id=pid, done_date=d, site=site, content=c)

    # ---- 写真 (番号は患者様の中の通し番号。撮影日が変わっても重ならない) ----
    for pid, shots in {
        H: [("2025-11-25", 4), ("2026-02-06", 4), ("2026-08-07", 4)],
        I: [("2026-05-15", 3), ("2026-08-14", 3)],
        T: [("2026-07-03", 2), ("2026-10-16", 2)],
        K: [("2026-08-21", 2), ("2026-10-30", 2)],
        M: [("2026-07-24", 3), ("2026-10-02", 3)],
    }.items():
        n = 0
        for d, count in shots:
            for _ in range(count):
                n += 1
                r.add("photos", patient_id=pid, number=n, taken_on=d, kind="intraoral", file="")

    # ---- 歯の状態 ----
    wisdom = [18, 28, 38, 48]
    missing = {H: wisdom + [14, 35], I: wisdom, M: wisdom,
               T: wisdom + [15, 16, 25, 26, 35, 36, 45, 46],  # ブリッジで補う
               K: [t for t in ALL_TEETH if t not in (13, 23, 33, 43)]}  # 義歯で補う
    for pid, items in {
        H: [(46, "RCT中"), (37, "CR"), (26, "クラウン"), (47, "CR"), (15, "C2")],
        I: [(16, "CR"), (26, "CR"), (46, "クラウン")],
        T: [(14, "ブリッジ支台"), (17, "ブリッジ支台"), (34, "ブリッジ支台"), (37, "ブリッジ支台"),
            (44, "ブリッジ支台"), (47, "ブリッジ支台")],
        K: [(13, "残根"), (23, "残根"), (33, "残根"), (43, "残根")],
        M: [(16, "C2"), (35, "CR")],
    }.items():
        for t, s in items:
            r.add("tooth_status", patient_id=pid, tooth=t, status=s)
    for pid, ts in missing.items():
        for t in ts:
            r.add("tooth_status", patient_id=pid, tooth=t, status="欠損")

    r.add("mucosal_conditions", patient_id=H, site="舌左縁", name="白板症")
    r.add("mucosal_conditions", patient_id=K, site="上顎前庭", name="義歯性口内炎")
    for pid, site, kind, made_by, made_on in [
        (H, "左下", "部分床義歯", "当院作成", "2026-05-08"),
        (K, "上顎", "総義歯", "当院作成", "2024-03-15"),
        (K, "下顎", "総義歯", "当院作成", "2024-03-15"),
        (T, "下顎", "ブリッジ", "他院作成", None),
    ]:
        r.add("dentures", patient_id=pid, site=site, kind=kind, made_by=made_by, made_on=made_on)

    # ---- 歯周基本検査 (花子の数字は 4mm以上6本・BOP 15%・PCR 18%、前回 9本・19%・24%) ----
    h_teeth = [t for t in ALL_TEETH if t not in missing[H]]
    nonlast = {t for i, t in enumerate(h_teeth) if i % 4 != 3 and i != 0}
    _perio(r, H, "2026-05-08", h_teeth, {16, 25, 26, 37, 46, 47, 24, 27, 45}, {16, 25, 26, 37, 46},
           set(h_teeth[:-1]))
    _perio(r, H, "2026-08-07", h_teeth, {16, 25, 26, 37, 46, 47}, {16, 26, 37, 46}, nonlast)
    i_teeth = [t for t in ALL_TEETH if t not in missing[I]]
    before = {i_teeth[i] for i in (0, 2, 5, 6, 9, 12, 14, 17, 20, 22, 24, 27)}
    after = {i_teeth[i] for i in (0, 2, 6, 9, 10, 13, 14, 17, 19, 22, 25)}
    _perio(r, I, "2026-05-15", i_teeth, before, set(sorted(before)[::2]), {t for t in i_teeth if t % 3 == 0})
    _perio(r, I, "2026-08-14", i_teeth, after, set(sorted(after)[::2]), {t for t in i_teeth if t % 4 == 0})
    t_teeth = [t for t in ALL_TEETH if t not in missing[T]]
    _perio(r, T, "2026-09-04", t_teeth, {14, 37, 44}, {14, 44}, {t for t in t_teeth if t % 5 == 0})
    _perio(r, K, "2026-09-25", [13, 23, 33, 43], {23}, {23}, {13, 33})
    m_teeth = [t for t in ALL_TEETH if t not in missing[M]]
    _perio(r, M, "2026-10-02", m_teeth, {16, 26}, {16}, {t for t in m_teeth if t % 6 == 0})

    # ---- メンテナンス間隔・ケア用品・物品・処方 ----
    for pid, months, last in [(H, 3, "2026-08-07"), (I, 3, "2026-08-14"), (T, 3, "2026-09-04"),
                              (K, 4, "2026-09-25"), (M, 6, "2026-10-02")]:
        r.add("maintenance_intervals", patient_id=pid, months=months, last_date=last)
    for pid, items in {
        H: [("歯間ブラシ SS", "2026-09-18"), ("フッ素ジェル", "2026-08-07"), ("歯ブラシ やわらかめ", "2026-08-07"),
            ("洗口液", "2026-05-08"), ("デンタルフロス", "2026-02-06")],
        I: [("歯間ブラシ M", "2026-08-14"), ("歯ブラシ ふつう", "2026-05-15")],
        T: [("義歯洗浄剤", "2026-09-04"), ("義歯ブラシ", "2026-07-03")],
        K: [("義歯洗浄剤", "2026-09-25"), ("義歯安定剤", "2026-08-21")],
        M: [("子ども用歯ブラシ", "2026-10-02"), ("フッ素ジェル", "2026-07-24")],
    }.items():
        for item, d in items:
            r.add("care_purchases", patient_id=pid, item=item, last_date=d)
    for pid, items in {
        H: [("2026-09-18", "歯間ブラシ SS", 2), ("2026-08-07", "フッ素ジェル", 1),
            ("2026-08-07", "歯ブラシ やわらかめ", 1), ("2026-05-08", "洗口液", 1), ("2026-02-06", "デンタルフロス", 2)],
        I: [("2026-08-14", "歯間ブラシ M", 2)],
        T: [("2026-09-04", "義歯洗浄剤", 1)],
        K: [("2026-09-25", "義歯洗浄剤", 1)],
        M: [("2026-10-02", "子ども用歯ブラシ", 2)],
    }.items():
        for d, item, q in items:
            r.add("goods_purchases", patient_id=pid, bought_on=d, item=item, qty=q)
    for pid, items in {
        H: [("2026-10-09", "ロキソプロフェン錠 60mg", "6錠"), ("2026-09-18", "クラリスロマイシン錠 200mg", "6錠"),
            ("2026-09-18", "ロキソプロフェン錠 60mg", "6錠")],
        I: [("2026-05-15", "ロキソプロフェン錠 60mg", "3錠")],
        T: [("2026-10-16", "ロキソプロフェン錠 60mg", "3錠")],
        K: [("2026-10-30", "ロキソプロフェン錠 60mg", "3錠")],
        M: [("2026-10-02", "ロキソプロフェン錠 60mg", "3錠")],
    }.items():
        for d, drug, amount in items:
            r.add("prescriptions", patient_id=pid, prescribed_on=d, drug=drug, amount=amount)

    # ---- G22 の追加 (全画面で遡るための古い記録と治療方針)。表ごとの id が変わらないよう、いつも一番最後に足す ----
    for d, site, c in [
        ("2025-10-17", "全顎", "SPT、歯周検査"),
        ("2025-09-12", "右上6番", "クラウン形成、印象"),
        ("2025-08-22", "右上6番", "支台築造"),
        ("2025-08-01", "右上6番", "根管充填"),
        ("2025-07-11", "右上6番", "根管貼薬、仮封"),
        ("2025-06-20", "右上6番", "抜髄、貼薬"),
        ("2025-05-23", "全顎", "SPT、スケーリング"),
        ("2025-04-18", "左下7番", "知覚過敏の処置"),
        ("2025-03-07", "全顎", "SPT、歯周検査"),
        ("2025-02-14", "右下7番", "CR充填"),
        ("2025-01-17", "全顎", "スケーリング"),
        ("2024-12-06", "右下7番", "C2の診断"),
    ]:
        r.add("treatment_history", patient_id=H, done_date=d, site=site, content=c)
    _perio(r, H, "2026-02-06", h_teeth, {16, 25, 26, 37, 46, 47, 24, 27, 45, 17}, {16, 25, 26, 37, 46, 17},
           set(h_teeth[1:-2]))
    _perio(r, H, "2025-10-17", h_teeth, {16, 25, 26, 37, 46, 47, 24, 27, 45, 17, 36, 15}, {16, 25, 26, 37, 46, 17, 36},
           set(h_teeth[:-3]))
    for pid, body in [
        (H, "歯髄は保存せず、根管治療のあと被せ物で噛める状態に戻す。歯周は3か月ごとに維持する"),
        (I, "歯周の状態を保つ。3か月ごとにSPTを続ける"),
        (T, "ブリッジの支台歯を守りながら、咬合を見て調整を続ける"),
        (K, "義歯の適合を保ち、疼痛が出た所を調整する"),
        (M, "右上6番はインレーで修復し、定期検診を6か月ごとに続ける"),
    ]:
        r.add("treatment_plans", patient_id=pid, seq=1, kind="policy", body=body)
    return dict(r)
