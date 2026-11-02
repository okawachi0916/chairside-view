"""本番の画面の HTML を作る。見た目と data-part は見本 (app/mockview) と同じにしてある。"""
from html import escape as h

from app.db import TODAY
from app.mockview.parts import FULL, MIC, PHONE, band, card
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


def _photos(numbers, cols_class, n=12):
    cells = "".join(f'<div class="ph">{x}</div>' for x in numbers)
    return f'<div class="photos {cols_class}" data-part="photo-list">{cells}</div>'


def intraoral(d, cols, cols_class):
    return card("intraoral-photos", "口腔内写真", _photos(d["photos"], cols_class), cols, actions=PHONE + FULL)


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
        f'data-date="{D.ja_date(x["taken_on"])}"><span class="ph">{x["number"]}</span>'
        f'<span>{D.ja_date(x["taken_on"])}</span></button>'
        for x in d["photo_rows"]
    )
    photos_t = (
        '<template data-fs="intraoral-photos" data-title="口腔内写真"><div class="fs-photos">'
        '<div class="fs-big"><div class="fs-big-box"></div><div class="fs-big-cap"></div></div>'
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
    return important_t + photos_t + spoken_t


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
    inner = f'<div class="teeth"><div class="frame"></div><div class="side">{lines}</div></div>'
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
UPPER = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
LOWER = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]
SIDE = {0: "l", 1: "r", 2: "t", 3: "b"}  # 近心・遠心・頬側・舌側 → 四角の4辺


def _plaque_svg(flags):
    sides = {SIDE[i] for i, c in enumerate(flags) if c == "1"}
    pts = {"t": "0,0 100,0 50,50", "r": "100,0 100,100 50,50", "b": "0,100 100,100 50,50", "l": "0,0 0,100 50,50"}
    polys = "".join(
        f'<polygon points="{p}" fill="{"#d32f2f" if k in sides else "#ffffff"}"/>' for k, p in pts.items()
    )
    return (
        '<svg viewBox="0 0 100 100" preserveAspectRatio="none">'
        f'{polys}<g stroke="#6b7480" stroke-width="1.5">'
        '<line x1="0" y1="0" x2="100" y2="100" vector-effect="non-scaling-stroke"/>'
        '<line x1="100" y1="0" x2="0" y2="100" vector-effect="non-scaling-stroke"/></g></svg>'
    )


def _perio(d):
    ex = d["perio"]
    if not ex:
        return card("perio-exam", "歯周基本検査", "", 12, actions=FULL)
    cur = ex[0]
    prev = ex[1] if len(ex) > 1 else None

    def cell(t, mid, make):
        if t not in cur["teeth"]:
            return f'<td class="gone{mid}">―</td>'
        return make(cur["teeth"][t], mid)

    def row(label, teeth, make, cls=""):
        cells = "".join(cell(t, " mid" if i == 8 else "", make) for i, t in enumerate(teeth))
        return f'<tr class="{cls}"><th class="row">{label}</th>{cells}</tr>'

    def pocket(t, mid):
        cls = ("deep " if t["pocket"] >= 4 else "") + ("bop " if t["bop"] else "")
        return f'<td class="{cls}{mid.strip()}">{t["pocket"]}</td>'

    def loose(t, mid):
        return f'<td class="{mid.strip()}">{t["mobility"]}</td>'

    def plaque(t, mid):
        return f'<td class="pl {mid.strip()}">{_plaque_svg(t["plaque"])}</td>'

    # 歯番は上顎と下顎で共通。真ん中から外へ 1〜8
    nos = "".join(
        f'<td class="{"mid" if i == 8 else ""}">{abs(i - 7.5) + 0.5:.0f}</td>' for i in range(16)
    )
    table = (
        '<table class="perio"><tbody>'
        + row("上顎 動揺度", UPPER, loose) + row("上顎 プラークチャート", UPPER, plaque, "plq")
        + row("上顎 ポケット", UPPER, pocket)
        + f'<tr class="no"><th class="row">歯番</th>{nos}</tr>'
        + row("下顎 ポケット", LOWER, pocket) + row("下顎 プラークチャート", LOWER, plaque, "plq")
        + row("下顎 動揺度", LOWER, loose)
        + "</tbody></table>"
    )

    def stat(label, key, unit):
        before = f" 前回 {prev[key]}{unit}" if prev else ""
        return f"<span>{label} <b>{cur[key]}{unit}</b>{before}</span>"

    stats = (
        '<div class="perio-stats">'
        + stat("4mm以上", "deep", "本") + stat("BOP", "bop", "%") + stat("PCR", "pcr", "%")
        + stat("動揺のある歯", "loose", "本")
        + f"<span>検査した歯 <b>{cur['n']}本</b></span></div>"
    )
    return card("perio-exam", "歯周基本検査", stats + table, 12, extra=f"検査日 {D.ja_date(cur['date'])}", actions=FULL)


def _hyg_side(d):
    iv = d["interval"]
    interval = ""
    if iv:
        last = f" 前回 {D.ja_date(iv['last_date'])}" if iv["last_date"] else ""
        interval = (f'<div><div class="lbl">メンテナンス間隔</div>'
                    f'<div class="kv"><b>{iv["months"]}か月ごと</b>{last}</div></div>')
    rows = "".join(f"<tr><td>{h(x['item'])}</td><td>{D.slash_date(x['last_date'])}</td></tr>" for x in d["care"])
    hist = (
        '<div class="fill"><div class="lbl">使用ケア用品・購入履歴</div>'
        '<table class="t"><thead><tr><th>品名</th><th>最後に買った日</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )
    return card("", "", interval + hist, 3, cls="side-card")


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
    recent = "".join(f"<tr><td>{D.ja_date(r['visit_date'])}</td><td>{h(r['treatment'] or '')}</td></tr>" for r in d["recent"])
    inner = (
        f'<div class="kv"><div>今回 <b>{D.ja_date(TODAY, week=True)}</b></div>'
        f'<div>時間 <b>{start}〜{end}（{D.duration(D.minutes(start, end)) if t else ""}）</b></div></div>'
        '<div class="fill"><div class="lbl">最近の来院</div>'
        f'<table class="t"><tbody>{recent}</tbody></table></div>'
    )
    return card("", "予約日時", inner, 4)


def _heat(d):
    grid = [[0] * 6 for _ in range(3)]
    for v in d["visits"]:
        day, hm = v.split(" ")
        wd = D.date.fromisoformat(day).weekday()
        if wd < 6:
            grid[_band_of(hm)][wd] += 1
    best = max(((grid[b][w], b, w) for b in range(3) for w in range(6)), key=lambda x: (x[0], -x[1], -x[2]))
    big = f"{D.WEEK[best[2]]}曜の{BANDS[best[1]]}" if best[0] else "―"
    head = "".join(f'<th class="n">{c}</th>' for c in D.WEEK[:6])
    rows = "".join(
        f'<tr><th>{BANDS[b]}</th>'
        + "".join(f'<td class="n{" hot" if v >= 5 else ""}">{v}</td>' for v in grid[b])
        + "</tr>"
        for b in range(3)
    )
    inner = (
        f'<div class="big-num">{big}</div>'
        f'<table class="t heat"><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table>'
    )
    return card("", "来院しやすい曜日・時間帯", inner, 5, extra=f"過去1年の来院{len(d['visits'])}回")


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
    nxt = ""
    if nx:
        who = " ".join(x for x in [D.ROLE_NAME.get(nx["staff_role"], ""), nx["staff_name"],
                                   f"{nx['minutes']}分枠" if nx["minutes"] else "", nx["timing"]] if x)
        nxt = f'<div class="next-big">{h(nx["body"])}<small>{h(who)}</small></div>'
    booked = "".join(
        f'<div class="kv">{D.ja_date(b["appt_date"])} {D.ROLE_NAME.get(b["role"], "")} {h(b["staff_name"])} '
        f'{h(b["reception_text"])}</div>' for b in d["booked"]
    )
    inner = (
        f'<div><div class="lbl">今日</div><div class="kv">{h(today_txt)}</div></div>'
        f'<div data-part="next-appointment"><div class="lbl">次回</div>{nxt}</div>'
        f'<div data-part="booked-appointment"><div class="lbl">予約済み</div>{booked}</div>'
    )
    return card("", "処置と次回の予約", inner, 4)


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
    memo = band("", "受付メモ", '<div class="big">' + "<br>".join(h(x) for x in d["memo"]) + "</div>")
    bands = f'<div class="bands two">{important(d)}{memo}</div>'
    body = (
        '<main class="body reception">'
        + _reserve(d) + _heat(d) + _cancel(d) + _next(d) + _goods(d) + _rx(d) + _back(d)
        + "</main>"
    )
    return top + bands + body


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
        "<script src='/static/js/mock_nav.js'></script></body></html>"
    )


def shell(kind, title):
    """/unit と /reception の入れ物。中身は毎回サーバーから読んで入れる。"""
    return (
        f"<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>{title}</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'>"
        "<link rel='stylesheet' href='/static/css/booklist.css'>"
        "<link rel='stylesheet' href='/static/css/unit.css'></head>"
        f"<body class='role-{'reception' if kind == 'reception' else 'doctor'}' data-kind='{kind}'>"
        "<div id='view' style='display:contents'></div>"
        + ("<div id='band' data-part='key-band' hidden><span data-band-text></span><span data-band-left></span></div>"
           "<script src='/static/js/voice_keys.js'></script>" if kind == "unit" else "")
        + "<script src='/static/js/actions.js'></script>"
        "<script src='/static/js/view.js'></script></body></html>"
    )
