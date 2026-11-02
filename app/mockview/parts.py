"""見本画面の共通の部品。HTML の文字列を返す。data-part は仕様の表と同じ値。"""

MIC = (
    '<svg class="mic" viewBox="0 0 24 24" aria-hidden="true">'
    '<path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.9V21h2v-3.1A7 7 0 0 0 19 11z"/>'
    "</svg>"
)

FULL = '<button class="mini" type="button" data-action="fullscreen">全画面</button>'
PHONE = '<button class="mini" type="button" data-action="phone">スマホ</button>'

PATIENT = "見本 花子 様 58歳 女性 No. 0123"
DATE = "2026年11月6日 金曜日"


def page(role, title, topbar, bands, body):
    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'>"
        f"</head><body class='role-{role}'>{topbar}{bands}{body}"
        "<script src='/static/js/mock_nav.js'></script></body></html>"
    )


def topbar(tag, appt_html, buttons, unit=True, mic=True):
    unit_s = " ユニット2" if unit else ""
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
    """cols は横12のうちの数。extra は題の横に出す字。part が空なら data-part は付けない。"""
    meta = f'<span class="meta">{extra}</span>' if extra else ""
    act = f'<span class="actions">{actions}</span>' if actions else ""
    dp = f' data-part="{part}"' if part else ""
    head = f'<div class="head"><h2>{title}</h2>{meta}{act}</div>' if title else ""
    return (
        f'<section class="card {cls}"{dp} style="grid-column: span {cols}">'
        f"{head}{inner}</section>"
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
    inner = (
        '<div class="inline"><span>高血圧、アムロジピン内服中</span>'
        "<span>脂質異常症、ロスバスタチン内服中</span>"
        "<span>骨粗鬆症、BP製剤内服中</span>"
        "<span>ペニシリン系抗菌薬アレルギー</span></div>"
    )
    return band("medical-history", "全身既往・服薬", inner)


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
        "intraoral-photos", "口腔内写真", photos(n, cols_class), cols, actions=PHONE + FULL
    )


def spoken(cols, lines, mmss):
    li = "".join(f"<li>{x}</li>" for x in lines)
    inner = f'<ul class="summary">{li}</ul>'
    rec = f'<div class="rec"><i></i>録音中 {mmss}</div>'
    return card("spoken-summary", "話した内容の整理", inner, cols, actions=FULL) + rec
