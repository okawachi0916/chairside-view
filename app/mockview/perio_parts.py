"""歯周検査の欄。見本（mockview/hygienist.py）と本物（views/render.py・全画面・入力）で同じ部品を使う。

基本検査と精密検査は同じ枠・同じ表で、違うのはポケットの行だけ（基本＝「PD」1行で1本に1マス、精密＝2行で1本に3マス）。
見る画面には「精密」「基本」の文字は出さない（マスの数を見れば分かる）。
exam は app/views/data.py の perio_exam() の形: {date, weekday, time, kind, teeth, n, bop, pcr, loose}。
"""
from datetime import date
from html import escape as h

from app.mockview.parts import FULL, card

TITLE = "歯周検査"

# 入力モードに入るボタン。押したときの動きは actions/perio.js
INPUT = '<button class="mini input" type="button" data-action="perio-input">入力</button>'

# 見ている向きで左から右へ。上顎 18〜11 | 21〜28、下顎 48〜41 | 31〜38。患者様の右が画面の左。
UPPER = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
LOWER = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]
WEEK = "月火水木金土日"

# 精密検査の6点の持ち方: 頬側（遠心・中央・近心）→ 舌側または口蓋側（遠心・中央・近心）
BUCCAL, INNER = 0, 3
KINDS = ("basic", "precise")

LEGEND = (
    '<span><b class="red">4</b> 赤の太字 = 出血(BOP)</span>'
    '<span><svg class="lg-tri" viewBox="0 0 10 10"><polygon points="0,0 10,5 0,10"/></svg> プラーク</span>'
    '<span><i class="lg-slash"></i> 斜線 = 欠損・対象外</span>'
)
LEGEND_3 = "<span>3マスは見たままの並び（右側の歯＝遠心・中央・近心／左側の歯＝近心・中央・遠心）</span>"


def plaque_svg(sides):
    """マス目いっぱいの長方形を × で4つに分ける。付いた面（t r b l）に色を付ける。色は CSS の変数。"""
    pts = {
        "t": "0,0 100,0 50,50",
        "r": "100,0 100,100 50,50",
        "b": "0,100 100,100 50,50",
        "l": "0,0 0,100 50,50",
    }
    polys = "".join(
        f'<polygon class="{"pq-on" if k in sides else "pq-off"}" data-side="{k}" points="{p}"/>'
        for k, p in pts.items()
    )
    return (
        '<svg viewBox="0 0 100 100" preserveAspectRatio="none">'
        f'{polys}<g class="pq-line" stroke-width="1.5">'
        '<line x1="0" y1="0" x2="100" y2="100" vector-effect="non-scaling-stroke"/>'
        '<line x1="100" y1="0" x2="0" y2="100" vector-effect="non-scaling-stroke"/></g></svg>'
    )


SIDE = {0: "l", 1: "r", 2: "t", 3: "b"}  # プラークの4文字（近心・遠心・頬側・舌側）→ 四角の4辺


def _val(v):
    return "" if v is None else str(v)


def _mid(i):
    return " mid" if i == 8 else ""


def _gone(i):
    return f'<td class="gone{_mid(i)}"></td>'


def _pocket(d, t, i):
    """基本検査: 1本に1マス。"""
    v, bop = d["pocket"], d["bop"]
    cls = ("bop " if bop else "") + ("todo " if v is None else "") + ("deep " if (v or 0) >= 4 else "")
    extra = f' data-v="{_val(v)}" data-bop="{1 if bop else 0}"'
    return f'<td class="{cls}{_mid(i)[1:]}" data-tooth="{t}" data-k="pocket"{extra}>{_val(v)}</td>'


def _three(d, t, i, base):
    """精密検査: 1本に3マス（見たままの並び。右側の歯＝遠心・中央・近心、左側の歯＝近心・中央・遠心）。"""
    order = (0, 1, 2) if t // 10 in (1, 4) else (2, 1, 0)
    cells = []
    for k in order:
        idx = base + k
        v, bop = d["pts"][idx], d["bops"][idx]
        cls = ("bop " if bop else "") + ("todo " if v is None else "")
        cells.append(f'<span class="{cls.strip()}" data-k="pt" data-i="{idx}" data-v="{_val(v)}" data-bop="{1 if bop else 0}">{_val(v)}</span>')
    return f'<td class="p3{_mid(i)}" data-tooth="{t}">{"".join(cells)}</td>'


def _loose(d, t, i):
    return f'<td class="{_mid(i)[1:]}" data-tooth="{t}" data-k="mob" data-v="{d["mobility"]}">{d["mobility"]}</td>'


def _plaque(d, t, i):
    sides = {SIDE[k] for k, c in enumerate(d["plaque"]) if c == "1"}
    return f'<td class="pl{_mid(i)}" data-tooth="{t}" data-k="plq">{plaque_svg(sides)}</td>'


def _row(exam, tooth_nos, make, label, cls=""):
    cells = "".join(
        _gone(i) if t not in exam["teeth"] else make(exam["teeth"][t], t, i)
        for i, t in enumerate(tooth_nos)
    )
    return f'<tr class="{cls}"><th class="row">{label}</th>{cells}</tr>'


def perio_table(exam):
    """表だけ。見る画面でも入力の画面でも、これを使う。"""
    precise = exam["kind"] == "precise"

    def pocket_rows(nos, upper):
        if not precise:
            return [_row(exam, nos, _pocket, "PD", "pd")]
        names = ("頬側", "口蓋側") if upper else ("舌側", "頬側")
        bases = (BUCCAL, INNER) if upper else (INNER, BUCCAL)
        return [_row(exam, nos, lambda d, t, i, b=b: _three(d, t, i, b), n, "pd3") for n, b in zip(names, bases)]

    band = "".join(f'<td class="{_mid(i)[1:]}">{abs(i - 7.5) + 0.5:.0f}</td>' for i in range(16))
    rows = (
        [_row(exam, UPPER, _loose, "動揺度", "mob")]
        + pocket_rows(UPPER, True)
        + [_row(exam, UPPER, _plaque, "プラーク", "plq")]
        + [f'<tr class="no"><th class="row"></th>{band}</tr>']
        + [_row(exam, LOWER, _plaque, "プラーク", "plq")]
        + pocket_rows(LOWER, False)
        + [_row(exam, LOWER, _loose, "動揺度", "mob")]
    )
    return (
        f'<table class="perio {"precise" if precise else "basic"}" data-kind="{exam["kind"]}">'
        '<colgroup><col class="lab">' + "<col>" * 16 + "</colgroup>"
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _stat(label, now, prev=None):
    before = f'<i>前回 {h(prev)}</i>' if prev else ""
    return f'<div class="st"><b>{now}</b><div class="lab"><small>{h(label)}</small>{before}</div></div>'


def _date_block(exam):
    y, m, d = (int(x) for x in exam["date"].split("-"))
    wd = WEEK[date(y, m, d).weekday()]
    t = f'<small class="tm">{h(exam["time"])}</small>' if exam.get("time") else ""
    return f'<div class="pdate"><b>{y}/{m}/{d}</b><em class="wd">({wd})</em>{t}</div>'


def perio_top(exam, prev):
    """上の帯: PCR・BOP率・動揺のある歯・検査した歯と、検査の日付。"""
    def pct(k):
        return f'{exam[k]}<u>%</u>', (f'{prev[k]}%' if prev else None)

    parts = (
        _stat("PCR", *pct("pcr")) + _stat("BOP率", *pct("bop"))
        + _stat("動揺のある歯（本数）", str(exam["loose"])) + _stat("検査した歯（本数）", str(exam["n"]))
    )
    return f'<div class="perio-top"><div class="perio-stats">{parts}</div>{_date_block(exam)}</div>'


def perio_body(exam, prev=None):
    legend = LEGEND + (LEGEND_3 if exam["kind"] == "precise" else "")
    return (
        perio_top(exam, prev)
        + '<div class="perio-lr"><span>右</span><span>左</span></div>'
        + perio_table(exam)
        + f'<div class="perio-legend">{legend}</div>'
    )


def perio_card(exam, prev=None):
    return card("perio-exam", TITLE, perio_body(exam, prev), 12, actions=INPUT + FULL, cls="perio-card")


def blank_exam(teeth, kind):
    """入力の画面用: 検査する歯だけを入れ、値は未入力にする。動揺度は 0、プラークは付いていない状態から始める。"""
    if kind not in KINDS:
        raise ValueError(kind)
    one = {"pocket": None, "bop": 0, "plaque": "0000", "mobility": 0,
           "pts": [None] * 6, "bops": [0] * 6}
    return {"date": "2000-01-01", "weekday": "", "time": "", "kind": kind, "n": len(teeth), "bop": 0, "pcr": 0, "loose": 0,
            "teeth": {t: {**one, "pts": [None] * 6, "bops": [0] * 6} for t in teeth}}
