"""見本画面の共通の部品。HTML の文字列を返す。data-part は仕様の表と同じ値。"""

MIC = (
    '<svg class="mic" viewBox="0 0 24 24" aria-hidden="true">'
    '<path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.9V21h2v-3.1A7 7 0 0 0 19 11z"/>'
    "</svg>"
)

# 全画面: 角を丸めた「広げる」記号つき。スマホ: 黒地に白抜きで、全画面と色を変える
EXPAND = (
    '<svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" '
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M3 7V5a2 2 0 0 1 2-2h2M13 3h2a2 2 0 0 1 2 2v2M17 13v2a2 2 0 0 1-2 2h-2M7 17H5a2 2 0 0 1-2-2v-2"/></svg>'
)
FULL = f'<button class="mini full" type="button" data-action="fullscreen">{EXPAND}<span>全画面</span></button>'
PHONE = '<button class="mini phone" type="button" data-action="phone">スマホで写真をやり取り</button>'

PATIENT = (
    '<b class="pname">見本 花子</b> 様 '
    '<span class="pinfo">58歳</span> <span class="pinfo">女性</span> '
    '<span class="pinfo">No. 0123</span>'
)
from app.today import ja_date as _ja, today as _today  # noqa: E402

DATE = _ja(_today(), week=True)


def page(role, title, topbar, bands, body):
    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'>"
        f"</head><body class='role-{role}'>{topbar}{bands}{body}"
        "<script src='/static/js/mock_nav.js'></script></body></html>"
    )


def topbar(tag, appt_html, buttons, unit=True, mic=True):
    unit_s = ' <span class="pinfo">ユニット2</span>' if unit else ""
    right = (MIC if mic else "") + "".join(
        f'<button type="button" data-action="{a}">{t}</button>' for a, t in buttons
    )
    return (
        '<header class="topbar">'
        f'<span class="role-tag">{tag}</span>'
        f'<span class="patient">{PATIENT}{unit_s}</span>'
        f'<span class="date">{DATE}</span>'
        f'<span class="appt" data-part="today-appointment">{appt_html}</span>'
        f'<span class="spacer"></span>{right}</header>'
    )


def card(part, title, inner, cols, extra="", actions="", cls=""):
    """cols は横12のうちの数。題だけを枠にかぶせ、extra（検査日など）とボタンは枠の中の右上に出す。"""
    meta = f'<span class="meta">{extra}</span>' if extra else ""
    tools = f'<div class="tools">{meta}{actions}</div>' if (extra or actions) else ""
    dp = f' data-part="{part}"' if part else ""
    head = f'<div class="head"><h2>{title}</h2></div>' if title else ""
    cls = f"{cls} has-tools" if tools else cls
    return (
        f'<section class="card {cls}"{dp}{f" style=\"grid-column: span {cols}\"" if cols else ""}>'
        f"{head}{tools}{inner}</section>"
    )


def band(part, title, inner, alert=False, full=True):
    cls = "band alert" if alert else "band"
    f = FULL if full else ""
    return f'<section class="{cls}"{(" data-part=\"" + part + "\"") if part else ""}><h2>{title}</h2>{inner}{f}</section>'


def important():
    lines = (
        '<div class="lines">ペニシリン系抗菌薬アレルギー<br>'
        "ビスホスホネート製剤服用中</div>"
    )
    return band("important", "重要事項", lines, alert=True)


def medical():
    items = [
        "高血圧（アムロジピン内服中）",
        "脂質異常症（ロスバスタチン内服中）",
        "骨粗鬆症（BP製剤内服中）",
        "ペニシリン系抗菌薬アレルギー",
    ]
    li = "".join(f"<li>{x}</li>" for x in items)
    return band("medical-history", "全身既往・服薬", f'<ul class="meds">{li}</ul>')


def note():
    inner = '<div class="big">長く口を開けているのがつらい方です</div>'
    return band("", "申し送り", inner, full=False)


def bands_three():
    return f'<div class="bands three">{important()}{medical()}{note()}</div>'


def photos(n, cols_class, part="photo-list"):
    cells = "".join(f'<div class="ph">{i}</div>' for i in range(1, n + 1))
    return f'<div class="photos {cols_class}" data-part="{part}">{cells}</div>'


def intraoral(cols, cols_class, n=12):
    return card(
        "intraoral-photos", "写真", photos(n, cols_class), cols, actions=PHONE + FULL
    )


def spoken(cols, lines, mmss):
    li = "".join(f"<li>{x}</li>" for x in lines)
    inner = f'<ul class="summary">{li}</ul>'
    rec = f'<div class="rec"><i></i>録音中 {mmss}</div>'
    return card("spoken-summary", "話した内容の整理", inner, cols, actions=FULL) + rec
