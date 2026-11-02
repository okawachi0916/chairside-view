"""歯周基本検査の欄。見本（mockview/hygienist.py）と本物（views/render.py）で共通に使う。"""
from html import escape as h

from app.mockview.parts import FULL, card

# 左から右へ、見ている向きで並べる。上顎 18〜11 | 21〜28、下顎 48〜41 | 31〜38。
UPPER = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
LOWER = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]


def plaque_svg(sides):
    """マス目いっぱいの長方形を × で4つに分ける。付いた面（t r b l）を赤くする。"""
    pts = {
        "t": "0,0 100,0 50,50",
        "r": "100,0 100,100 50,50",
        "b": "0,100 100,100 50,50",
        "l": "0,0 0,100 50,50",
    }
    polys = "".join(
        f'<polygon points="{p}" fill="{"#d32f2f" if k in sides else "#ffffff"}"/>'
        for k, p in pts.items()
    )
    return (
        '<svg viewBox="0 0 100 100" preserveAspectRatio="none">'
        f'{polys}<g stroke="#6b7480" stroke-width="1.5">'
        '<line x1="0" y1="0" x2="100" y2="100" vector-effect="non-scaling-stroke"/>'
        '<line x1="100" y1="0" x2="0" y2="100" vector-effect="non-scaling-stroke"/></g></svg>'
    )


def _cells(teeth, tooth_nos, make):
    out = []
    for i, t in enumerate(tooth_nos):
        mid = "mid" if i == 8 else ""
        d = teeth.get(t)
        out.append(f'<td class="gone {mid}">―</td>' if d is None else make(d, mid))
    return "".join(out)


def _pocket(d, mid):
    cls = ("deep " if d["pocket"] >= 4 else "") + ("bop " if d["bop"] else "")
    return f'<td class="{cls}{mid}">{d["pocket"]}</td>'


def _loose(d, mid):
    return f'<td class="{mid}">{d["mobility"]}</td>'


def _plaque(d, mid):
    return f'<td class="pl {mid}">{plaque_svg(d["sides"])}</td>'


def _stat(label, now, prev):
    before = f"前回 {h(prev)}" if prev else "&nbsp;"
    return f'<div class="st"><small>{h(label)}</small><b>{h(now)}</b><em>{before}</em></div>'


def perio_card(teeth, stats, date_txt):
    """teeth: 歯番 → {pocket, bop, mobility, sides}。欠けた歯は入れない。
    stats: (項目名, 今の値, 前回の値 または None) の並び。"""
    nos = "".join(
        f'<td class="{"mid" if i == 8 else ""}">{abs(i - 7.5) + 0.5:.0f}</td>' for i in range(16)
    )

    def row(label, tooth_nos, make, cls="", grp=""):
        return f'<tr class="{cls}">{grp}<th class="row">{label}</th>{_cells(teeth, tooth_nos, make)}</tr>'

    table = (
        '<table class="perio"><tbody>'
        + row("動揺度", UPPER, _loose, grp='<th class="grp" rowspan="3">上顎</th>')
        + row("プラークチャート", UPPER, _plaque, "plq")
        + row("ポケット", UPPER, _pocket)
        + f'<tr class="no"><th class="row" colspan="2">歯番</th>{nos}</tr>'
        + row("ポケット", LOWER, _pocket, grp='<th class="grp" rowspan="3">下顎</th>')
        + row("プラークチャート", LOWER, _plaque, "plq")
        + row("動揺度", LOWER, _loose)
        + "</tbody></table>"
    )
    st = '<div class="perio-stats">' + "".join(_stat(*s) for s in stats) + "</div>"
    return card(
        "perio-exam", "歯周基本検査", st + table, 12, extra=f"検査日 {date_txt}", actions=FULL
    )
