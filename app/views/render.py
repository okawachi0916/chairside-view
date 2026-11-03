"""本番の画面の HTML を作る。見た目と data-part は見本 (app/mockview) と同じにしてある。"""
from html import escape as h

from app.db import TODAY
from app.mockview.parts import FULL, MIC, PHONE, band, card
from app.views import photos as PH
from app.mockview.reception_parts import heat_card, next_card, reserve_card
from app.mockview.perio_parts import perio_card
from app.mockview import tooth_chart as TC
from app.views import data as D

BAND = {1: "n1", 2: "n2", 3: "n3", 4: "n4"}


def topbar(tag, patient, appt, buttons, mic=True):
    right = (MIC if mic else "") + "".join(
        f'<button type="button" data-action="{a}">{t}</button>' for a, t in buttons
    )
    return (
        '<header class="topbar">'
        f'<span class="role-tag">{tag}</span>'
        f'<span class="patient">{patient}</span>'
        f'<span class="date">{D.ja_date(TODAY, week=True)}</span>'
        f'<span class="appt" data-part="today-appointment">{appt}</span>'
        f'<span class="spacer"></span>{right}</header>'
    )


def patient_label(p, unit=None):
    s = f"{h(p['name'])} 様 {p['age']}歳 {h(p['sex'])} No. {h(p['chart_no'])}"
    return s + (f" ユニット{unit}" if unit else "")


def important(d):
    items = d["important"]
    if len(items) > 4:
        items = items[:3] + [f"ほか {len(items) - 3}件"]
    cls = BAND.get(len(items), "n4")
    lines = f'<div class="lines {cls}">' + "<br>".join(h(x) for x in items) + "</div>"
    return band("important", "重要事項", lines, alert=True)


def medical(d):
    spans = "".join(
        "<span>" + h(m["condition"] + ("、" + m["medication"] if m["medication"] else "")) + "</span>"
        for m in d["medical"]
    )
    return band("medical-history", "全身既往・服薬", f'<div class="inline">{spans}</div>')


def handover(d):
    inner = '<div class="big">' + "<br>".join(h(x) for x in d["handover"]) + "</div>"
    return band("", "申し送り", inner, full=False)


def bands_three(d):
    return f'<div class="bands three">{important(d)}{medical(d)}{handover(d)}</div>'


def appt_text(d):
    a = d["appt"]
    main = f"{a['start_time']}〜{a['end_time']}（{D.duration(D.minutes(a['start_time'], a['end_time']))}）"
    small = ""
    for o in d["day"]:
        if o["id"] == a["id"]:
            continue
        pre = "前の予約 " if o["start_time"] < a["start_time"] else ""
        small += f"<small>{pre}{o['start_time']}〜{o['end_time']} {h(o['treatment'])}</small>"
    return main + small


def _tile(x):
    return (f'<div class="ph" data-n="{x["number"]}"><img src="{PH.url_for(x["number"], x["file"])}" alt="" loading="lazy">'
            f'<span class="no">{x["number"]}</span></div>')


def _photos(rows):
    """撮影日ごとにまとめ、新しい日から左上へ並べる。古い日はスクロールで見る。"""
    days = {}
    for x in rows:
        days.setdefault(x["taken_on"], []).append(x)
    groups = "".join(
        f'<div class="pg"><div class="pg-date">{D.ja_date(day)}</div>'
        f'<div class="pg-tiles">{"".join(_tile(x) for x in days[day])}</div></div>'
        for day in sorted(days, reverse=True)
    )
    return f'<div class="photos pgroups" data-part="photo-list">{groups}</div>'


def intraoral(d, cols, cols_class):
    return card("intraoral-photos", "口腔内写真", _photos(d["photo_rows"]), cols, actions=PHONE + FULL)


def spoken(d, cols):
    li = "".join(f"<li>{h(x)}</li>" for x in d["summary"])
    return card("spoken-summary", "話した内容の整理", f'<ul class="summary">{li}</ul>', cols, actions=FULL)


def fullscreen_templates(d):
    """全画面にする3つの部品の中身。<template> なので、開くまでページの文字には出ない。"""
    rows = "".join(
        f'<div class="fs-row"><b>{h(x["body"])}</b> '
        + (f'<span>{h(" ".join(v for v in (x["period"], x["detail"]) if v))}</span>' if x["period"] or x["detail"] else "")
        + "</div>"
        for x in d["important_full"]
    )
    important_t = (
        '<template data-fs="important" data-title="重要事項">'
        f'<div class="fs-scroll fs-important">{rows}</div></template>'
    )
    items = "".join(
        f'<button type="button" class="fs-item" data-action="fs-photo" data-n="{x["number"]}" '
        f'data-date="{D.ja_date(x["taken_on"])}" data-src="{PH.url_for(x["number"], x["file"])}">'
        f'<span class="ph"><img src="{PH.url_for(x["number"], x["file"])}" alt=""><span class="no">{x["number"]}</span></span>'
        f'<span class="dt">{D.ja_date(x["taken_on"])}</span></button>'
        for x in reversed(d["photo_rows"])
    )
    photos_t = (
        '<template data-fs="intraoral-photos" data-title="口腔内写真"><div class="fs-photos">'
        '<div class="fs-big"><div class="fs-big-box"></div></div>'
        f'<div class="fs-scroll fs-list">{items}</div></div></template>'
    )
    li = "".join(f"<li>{h(x)}</li>" for x in d["summary"])
    talk = h(d["transcript"])
    spoken_t = (
        '<template data-fs="spoken-summary" data-title="話した内容の整理"><div class="fs-cols">'
        f'<div class="fs-col"><h3>要約</h3><div class="fs-scroll"><ul>{li}</ul></div></div>'
        f'<div class="fs-col"><h3>話したままの文字</h3><div class="fs-scroll"><p>{talk}</p></div></div>'
        "</div></template>"
    )
    return important_t + photos_t + spoken_t + _fs_medical(d) + (_fs_doctor(d) if d["role"] == "doctor" else _fs_perio(d))


def _tpl(part, title, inner):
    return f'<template data-fs="{part}" data-title="{title}">{inner}</template>'


def _fs_medical(d):
    rows = "".join(
        f'<tr><td class="b">{h(m["condition"])}</td><td>{h(m["medication"])}</td><td>{h(m["since"])}</td><td>{h(m["clinic"])}</td></tr>'
        for m in d["medical"]
    )
    return _tpl("medical-history", "全身既往・服薬",
                '<div class="fs-scroll"><table class="fs-table"><thead><tr><th>病名</th><th>薬</th><th>いつから</th><th>通院先</th></tr></thead>'
                f"<tbody>{rows}</tbody></table></div>")


def _fs_doctor(d):
    """今日の処置・治療計画・治療方針・過去の診療メモを同時に広げる。治療歴は行を増やして遡る。"""
    a = d["appt"]
    plan = "".join(f"<li>{h(x)}</li>" for x in d["plan"])
    policy = "".join(f"<p>{h(x)}</p>" for x in d["policy"])
    notes = "".join(
        f'<div class="fs-note"><b>{D.ja_date(n["note_date"])}{" 歯科衛生士" if n["author_role"] == "hygienist" else ""}</b> {h(n["body"])}</div>'
        for n in d["notes"]
    )
    today = _tpl("today-treatment", "今日の処置",
                 '<div class="fs-cols"><div class="fs-col"><div class="fs-scroll">'
                 f'<h3>今日の処置</h3><p class="fs-big-line">{h(a["detail"] or a["treatment"])}</p><p>{h(a["detail_sub"])}</p>'
                 f"<h3>治療計画</h3><ul>{plan}</ul><h3>治療方針</h3>{policy}</div></div>"
                 f'<div class="fs-col"><h3>過去の診療メモ</h3><div class="fs-scroll">{notes}</div></div></div>')
    rows = "".join(
        f"<tr><td>{D.slash_date(x['done_date'])}</td><td>{h(x['site'])}</td><td>{h(x['content'])}</td></tr>"
        for x in d["history"]
    )
    hist = _tpl("treatment-history", "治療歴",
                '<div class="fs-scroll"><table class="fs-table"><thead><tr><th>日付</th><th>部位</th><th>内容</th></tr></thead>'
                f"<tbody>{rows}</tbody></table></div>")
    return today + hist


UPPER = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
LOWER = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]


def _perio_col(ex, label):
    def cell(t):
        v = ex["teeth"].get(t)
        if not v:
            return f'<div class="pc none"><i>{t}</i></div>'
        cls = " deep" if v["pocket"] >= 4 else ""
        return (f'<div class="pc{cls}"><i>{t}</i><b>{v["pocket"]}</b>'
                f'<u class="bop">{"●" if v["bop"] else ""}</u>{"<em>動</em>" if v["mobility"] else ""}</div>')

    stats = (f'4mm以上 {ex["deep"]}本　BOP {ex["bop"]}%　PCR {ex["pcr"]}%　動揺 {ex["loose"]}本　検査した歯 {ex["n"]}本')
    return (f'<div class="fs-col pcol"><h3>{label} {D.ja_date(ex["date"])}</h3><div class="pstat">{stats}</div>'
            f'<div class="pgrid">{"".join(cell(t) for t in UPPER)}</div>'
            f'<div class="pgrid">{"".join(cell(t) for t in LOWER)}</div></div>')


def _fs_perio(d):
    """新しい検査から順に、前回と今回を前後に並べる。1ページに1組。ページ送りで過去の検査へ遡る。"""
    ex = d["perio_all"]
    if not ex:
        return _tpl("perio-exam", "歯周基本検査", '<div class="fs-scroll"><p>検査の記録はありません</p></div>')
    pages = []
    for i in range(max(1, len(ex) - 1)):
        new = ex[i]
        old = ex[i + 1] if i + 1 < len(ex) else None
        first = i == 0
        left = _perio_col(old, "前回" if first else "前の検査") if old else ""
        right = _perio_col(new, "今回" if first else "この検査")
        pages.append(f'<section class="fs-page"><div class="fs-cols">{left}{right}</div></section>')
    return _tpl("perio-exam", "歯周基本検査", f'<div class="fs-scroll" data-pages>{"".join(pages)}</div>')


def _fs_memo(d):
    rows = "".join(
        f'<div class="fs-row"><b>{h(m["body"])}</b> ' + (f'<span>{h(m["written_on"])}</span>' if m["written_on"] else "") + "</div>"
        for m in d["memo_full"]
    )
    return _tpl("reception-memo", "受付メモ", f'<div class="fs-scroll fs-important">{rows}</div>')


# ---------- 歯科医師 ----------
def _months_since(s):
    """経過した月数。日数から四捨五入する (2026年5月8日から6か月)。"""
    days = (D.date.fromisoformat(TODAY) - D.date.fromisoformat(s)).days
    return round(days / 30.4375)


def _doctor_today(d):
    a = d["appt"]
    notes = "".join(
        f'<div class="n{" hyg" if n["author_role"] == "hygienist" else ""}">{D.ja_date(n["note_date"])} '
        f'{"歯科衛生士 " if n["author_role"] == "hygienist" else ""}{h(n["body"])}</div>'
        for n in d["notes"]
    )
    plan = "".join(f"<div>{h(x)}</div>" for x in d["plan"])
    inner = (
        '<div class="today">'
        f'<div class="main">{h(a["detail"] or a["treatment"])}</div><div class="sub">{h(a["detail_sub"])}</div></div>'
        f'<div class="plan" data-part="treatment-plan"><h3>治療計画</h3>{plan}</div>'
        '<h3 class="notes-h">過去の診療メモ</h3>'
        f'<div class="notes" data-part="past-notes">{notes}</div>'
    )
    return card("today-treatment", "今日の処置", inner, 4, actions=FULL)


def _doctor_history(d):
    rows = "".join(
        f"<tr><td>{D.slash_date(x['done_date'])}</td><td>{h(x['site'])}</td><td>{h(x['content'])}</td></tr>"
        for x in d["history"][:10]
    )
    inner = (
        '<table class="t"><thead><tr><th>日付</th><th>部位</th><th>内容</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )
    return card("treatment-history", "治療歴", inner, 3, actions=FULL)


def _doctor_teeth(d):
    lines = "".join(f"<div><b>その他粘膜疾患</b> <span>{h(m['site'])} {h(m['name'])}</span></div>" for m in d["mucosal"])
    for x in d["dentures"]:
        t = f"{x['site']} {x['kind']}"
        if x["made_by"]:
            t += f" {x['made_by']}"
        if x["made_on"]:
            t += f" {D.ja_date(x['made_on'])} 経過期間 {_months_since(x['made_on'])}か月"
        lines += f"<div><b>義歯</b> <span>{h(t)}</span></div>"
    own = TC.own_teeth(d["teeth"], [x["site"] for x in d["history"]], d["dentures"])
    today = TC.today_teeth(a["detail"] for a in d["day"] if a["role"] == "doctor")
    svg = TC.chart_svg(d["teeth"], own, today)
    inner = f'<div class="teeth"><div class="frame">{svg}</div><div class="side">{lines}{TC.LEGEND}</div></div>'
    return card("tooth-chart", "歯の状態", inner, 8)


def doctor_page(d):
    top = topbar("歯科医師用", patient_label(d["patient"], d["appt"]["unit"]), appt_text(d),
                 [("change-patient", "患者様を変える"), ("change-role", "役割を変える")])
    body = (
        '<main class="body doctor">'
        + _doctor_today(d) + _doctor_history(d) + intraoral(d, 5, "c4") + _doctor_teeth(d) + spoken(d, 4)
        + "</main>"
    )
    return top + bands_three(d) + body + fullscreen_templates(d)


# ---------- 歯科衛生士 ----------
SIDE = {0: "l", 1: "r", 2: "t", 3: "b"}  # 近心・遠心・頬側・舌側 → 四角の4辺


def _perio(d):
    ex = d["perio"]
    if not ex:
        return card("perio-exam", "歯周基本検査", "", 12, actions=FULL)
    cur = ex[0]
    prev = ex[1] if len(ex) > 1 else None
    teeth = {
        t: {"pocket": v["pocket"], "bop": v["bop"], "mobility": v["mobility"],
            "sides": {SIDE[i] for i, c in enumerate(v["plaque"]) if c == "1"}}
        for t, v in cur["teeth"].items()
    }

    def stat(label, key, unit):
        return (label, f"{cur[key]}{unit}", f"{prev[key]}{unit}" if prev else None)

    stats = [stat("4mm以上", "deep", "本"), stat("BOP", "bop", "%"), stat("PCR", "pcr", "%"),
             stat("動揺のある歯", "loose", "本"), ("検査した歯", f"{cur['n']}本", None)]
    return perio_card(teeth, stats, D.ja_date(cur["date"]))


def _hyg_side(d):
    iv = d["interval"]
    last = f' <span class="prev">前回 {D.ja_date(iv["last_date"])}</span>' if iv and iv["last_date"] else ""
    interval = card("", "メンテナンス間隔",
                    f'<div class="kv"><b>{iv["months"]}か月ごと</b>{last}</div>' if iv else "", None)
    rows = "".join(f"<tr><td>{h(x['item'])}</td><td>{D.slash_date(x['last_date'])}</td></tr>" for x in d["care"])
    hist = card("", "使用ケア用品・購入履歴",
                '<table class="t"><thead><tr><th>品名</th><th>最後に買った日</th></tr></thead>'
                f"<tbody>{rows}</tbody></table>", None)
    return f'<div class="stack" style="grid-column: span 3">{interval}{hist}</div>'


def hygienist_page(d):
    top = topbar("歯科衛生士用", patient_label(d["patient"], d["appt"]["unit"]), appt_text(d),
                 [("change-patient", "患者様を変える"), ("change-role", "役割を変える")])
    body = (
        '<main class="body hygienist">'
        + intraoral(d, 6, "c6") + spoken(d, 3) + _hyg_side(d) + _perio(d)
        + "</main>"
    )
    return top + bands_three(d) + body + fullscreen_templates(d)


# ---------- 受付 ----------
BANDS = ["午前", "午後", "夕方"]


def _band_of(hm):
    return 0 if hm < "12:00" else (1 if hm < "17:00" else 2)


def _reserve(d):
    t = d["today"]
    start, end = (t[0]["start_time"], t[-1]["end_time"]) if t else ("", "")
    dur = D.duration(D.minutes(start, end)) if t else ""
    recent = [(D.ja_date(r["visit_date"]), r["treatment"] or "") for r in d["recent"]]
    return reserve_card(D.ja_date(TODAY, week=True), f"{start}〜{end}（{dur}）", recent)


def _heat(d):
    grid = [[0] * 6 for _ in range(3)]
    for v in d["visits"]:
        day, hm = v.split(" ")
        wd = D.date.fromisoformat(day).weekday()
        if wd < 6:
            grid[_band_of(hm)][wd] += 1
    best = max(((grid[b][w], b, w) for b in range(3) for w in range(6)), key=lambda x: (x[0], -x[1], -x[2]))
    big = f"{D.WEEK[best[2]]}曜の{BANDS[best[1]]}" if best[0] else "―"
    return heat_card(grid, BANDS, big, len(d["visits"]))


def _cancel(d):
    cs = d["cancels"]
    no_show = sum(c["no_show"] for c in cs)
    lines = "".join(
        f'<div class="kv">{D.slash_date(c["cancel_date"])}({D.WEEK[D.date.fromisoformat(c["cancel_date"]).weekday()]}) '
        f'{h(c["reason"])}</div>' for c in cs[:3]
    )
    inner = (
        f'<div class="big-num">{len(cs)}回</div>'
        f'<div class="kv">予約{d["appt_count"]}回のうち 無断キャンセル {no_show}回</div>'
        f'<div><div class="lbl">キャンセルした日</div>{lines}</div>'
    )
    return card("", "キャンセル傾向", inner, 3)


def _next(d):
    today_txt = "、".join(a["reception_text"] or a["treatment"] for a in d["today"])
    nx = d["next"]
    body, chips = "", []
    if nx:
        body = nx["body"]
        who = " ".join(x for x in [D.ROLE_NAME.get(nx["staff_role"], ""), nx["staff_name"]] if x)
        chips = [x for x in [who, f"{nx['minutes']}分枠" if nx["minutes"] else "", nx["timing"]] if x]
    booked = [
        (D.ja_date(b["appt_date"]),
         " ".join(x for x in [D.ROLE_NAME.get(b["role"], ""), b["staff_name"], b["reception_text"]] if x))
        for b in d["booked"]
    ]
    return next_card(today_txt, body, chips, booked)


def _goods(d):
    rows = "".join(
        f'<tr><td>{D.slash_date(x["bought_on"])}</td><td>{h(x["item"])}</td><td class="n">{x["qty"]}</td></tr>'
        for x in d["goods"][:5]
    )
    inner = (
        '<table class="t"><thead><tr><th>買った日</th><th>品名</th><th class="n">数</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )
    return card("", "過去の物品購入", inner, 3)


def _rx(d):
    rows = "".join(
        f"<tr><td>{D.slash_date(x['prescribed_on'])}</td><td>{h(x['drug'])}</td><td>{h(x['amount'])}</td></tr>"
        for x in d["rx"][:3]
    )
    inner = (
        '<table class="t"><thead><tr><th>処方日</th><th>薬</th><th>量</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )
    return card("", "過去の処方", inner, 3)


def _back(d):
    b = d["booked"][0] if d["booked"] else None
    if b:
        dt = D.date.fromisoformat(b["appt_date"])
        txt = f"次回のご予約 {dt.month}月{dt.day}日({D.WEEK[dt.weekday()]}) {b['start_time']}"
    else:
        txt = "次回のご予約 ―"
    return card("", "診察券 裏面", f'<div class="card-back">{txt}</div>', 2)


def reception_page(d):
    appt = ""
    for i, a in enumerate(d["today"]):
        t = f"{a['start_time']}〜{a['end_time']} {h(a['treatment'])}"
        appt += t if i == 0 else f"<small>{t}</small>"
    top = topbar("受付用", patient_label(d["patient"], d["today"][0]["unit"] if d["today"] else None), appt,
                 [("change-patient", "患者様を変える")], mic=False)
    memo = band("reception-memo", "受付メモ", '<div class="big">' + "<br>".join(h(x) for x in d["memo"]) + "</div>")
    bands = f'<div class="bands two">{important(d)}{memo}</div>'
    body = (
        '<main class="body reception">'
        + _reserve(d) + _heat(d) + _cancel(d) + _next(d) + _goods(d) + _rx(d) + _back(d)
        + "</main>"
    )
    return top + bands + body + _reception_templates(d)


def _reception_templates(d):
    """受付の全画面は、重要事項と受付メモだけ。マウスで開く (声の言葉には足さない)。"""
    rows = "".join(
        f'<div class="fs-row"><b>{h(x["body"])}</b> '
        + (f'<span>{h(" ".join(v for v in (x["period"], x["detail"]) if v))}</span>' if x["period"] or x["detail"] else "")
        + "</div>" for x in d["important_full"]
    )
    return _tpl("important", "重要事項", f'<div class="fs-scroll fs-important">{rows}</div>') + _fs_memo(d)


def reception_chooser(rows):
    body = ""
    for p in rows:
        t = "　".join(f"{a['start_time']}〜{a['end_time']} {h(a['treatment'])}" for a in p["today"])
        body += (
            f'<tr class="row" tabindex="0" role="button" data-patient="{p["id"]}">'
            f'<td class="no">{h(p["chart_no"])}</td>'
            f'<td class="name"><span class="nm" data-name="{h(p["name"])}">●● ●●</span>'
            '<button type="button" class="mini reveal" data-action="reveal">表示</button></td>'
            f'<td class="time">{t}</td></tr>'
        )
    top = ('<header class="topbar"><span class="role-tag">受付用</span>'
           f'<span class="date">{D.ja_date(TODAY, week=True)}</span></header>')
    return (
        top + '<main class="list" data-part="appointment-list"><table class="book">'
        "<thead><tr><th>カルテ番号</th><th>氏名</th><th>今日の予約</th></tr></thead>"
        f"<tbody>{body}</tbody></table></main>"
    )


# ---------- 予約一覧 ----------
def list_page(rows):
    body = ""
    for r in rows:
        url = f"/unit?appt={r['id']}&role={r['role']}"
        body += (
            f'<tr class="row" tabindex="0" role="link" data-href="{url}" data-proc="{h(r["treatment"])}">'
            f'<td class="time">{r["start_time"]}〜{r["end_time"]}</td><td class="no">{h(r["chart_no"])}</td>'
            f'<td class="name"><span class="nm" data-name="{h(r["name"])}">●● ●●</span>'
            '<button type="button" class="mini reveal" data-action="reveal">表示</button></td>'
            f'<td class="proc">{h(r["treatment"])}</td></tr>'
        )
    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>予約一覧</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'>"
        "<link rel='stylesheet' href='/static/css/booklist.css'></head><body class='role-list'>"
        f'<header class="topbar"><span class="role-tag">予約一覧</span><span class="date">{D.ja_date(TODAY, week=True)}</span></header>'
        '<main class="list" data-part="appointment-list"><table class="book">'
        "<thead><tr><th>時間</th><th>カルテ番号</th><th>氏名 "
        '<button type="button" class="mini" data-action="reveal-all">すべて表示</button></th>'
        f"<th>処置</th></tr></thead><tbody>{body}</tbody></table></main>"
        "<script src='/static/js/mock_nav.js'></script>"
        "<script src='/static/js/voice_keys.js'></script><script src='/static/js/rec_keys.js'></script></body></html>"
    )


def shell(kind, title):
    """/unit と /reception の入れ物。中身は毎回サーバーから読んで入れる。"""
    return (
        f"<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>{title}</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'>"
        "<link rel='stylesheet' href='/static/css/booklist.css'>"
        "<link rel='stylesheet' href='/static/css/unit.css'>"
        "<link rel='stylesheet' href='/static/css/photos.css'></head>"
        f"<body class='role-{'reception' if kind == 'reception' else 'doctor'}' data-kind='{kind}'>"
        "<div id='view' style='display:contents'></div>"
        + ("<div id='band' data-part='key-band' hidden><span data-band-text></span><span data-band-left></span></div>"
           "<script src='/static/js/voice_keys.js'></script>" if kind == "unit" else "")
        + "<script src='/static/js/actions.js'></script>"
        + ("<script src='/static/js/actions/voice.js'></script><script src='/static/js/actions/ai.js'></script><script src='/static/js/actions/rec.js'></script><script src='/static/js/actions/phone.js'></script><script src='/static/js/actions/perio.js'></script>"
           if kind == "unit" else "")
        + "<script src='/static/js/view.js'></script></body></html>"
    )
