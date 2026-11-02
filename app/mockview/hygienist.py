from app.mockview.parts import FULL, bands_three, card, intraoral, page, spoken, topbar

PURCHASES = [
    ("歯間ブラシ SS", "2026/9/18"),
    ("フッ素ジェル", "2026/8/7"),
    ("歯ブラシ やわらかめ", "2026/8/7"),
    ("洗口液", "2026/5/8"),
    ("デンタルフロス", "2026/2/6"),
]

# 左から右へ、見ている向きで並べる。上顎 18〜11 | 21〜28、下顎 48〜41 | 31〜38。
UPPER = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
LOWER = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]
MISSING = {18, 28, 38, 48, 14, 35}  # 欠けている6本。検査した歯は26本

POCKET = {
    17: 3, 16: 4, 15: 3, 13: 3, 12: 2, 11: 3, 21: 2, 22: 3, 23: 3, 24: 3, 25: 4, 26: 5, 27: 3,
    47: 4, 46: 4, 45: 3, 44: 3, 43: 2, 42: 2, 41: 3, 31: 2, 32: 2, 33: 3, 34: 3, 36: 3, 37: 4,
}
BOP = {16, 26, 46, 37, 25, 11}
LOOSE = {26: 1}
# プラーク: 付いた面 t=上 r=右 b=下 l=左
PLAQUE = {
    16: "b", 26: "bl", 46: "t", 47: "r", 36: "tl", 37: "t", 15: "b", 25: "l", 17: "r",
    27: "b", 11: "r", 21: "l",
}


def _plaque_svg(sides):
    """マス目いっぱいの長方形を × で4つに分ける。付いた面を赤くする。"""
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
        f'{polys}<g stroke="#6b7480" stroke-width="1.5" vector-effect="non-scaling-stroke">'
        '<line x1="0" y1="0" x2="100" y2="100" vector-effect="non-scaling-stroke"/>'
        '<line x1="100" y1="0" x2="0" y2="100" vector-effect="non-scaling-stroke"/></g></svg>'
    )


def _cells(teeth, make):
    out = []
    for i, t in enumerate(teeth):
        mid = " mid" if i == 8 else ""
        if t in MISSING:
            out.append(f'<td class="gone{mid}">―</td>')
        else:
            out.append(make(t, mid))
    return "".join(out)


def _row(label, teeth, make, cls=""):
    return f'<tr class="{cls}"><th class="row">{label}</th>{_cells(teeth, make)}</tr>'


def _pocket(t, mid):
    v = POCKET[t]
    cls = ("deep " if v >= 4 else "") + ("bop " if t in BOP else "")
    return f'<td class="{cls}{mid.strip()}">{v}</td>'


def _loose(t, mid):
    return f'<td class="{mid.strip()}">{LOOSE.get(t, 0)}</td>'


def _plaque(t, mid):
    return f'<td class="pl {mid.strip()}">{_plaque_svg(PLAQUE.get(t, ""))}</td>'


def _perio():
    # 歯番は上顎と下顎で共通。真ん中から外へ 1〜8
    nos = "".join(
        f'<td class="{"mid" if i == 8 else ""}">{abs(i - 7.5) + 0.5:.0f}</td>' for i in range(16)
    )
    table = (
        '<table class="perio"><tbody>'
        + _row("上顎 動揺度", UPPER, _loose)
        + _row("上顎 プラークチャート", UPPER, _plaque, "plq")
        + _row("上顎 ポケット", UPPER, _pocket)
        + f'<tr class="no"><th class="row">歯番</th>{nos}</tr>'
        + _row("下顎 ポケット", LOWER, _pocket)
        + _row("下顎 プラークチャート", LOWER, _plaque, "plq")
        + _row("下顎 動揺度", LOWER, _loose)
        + "</tbody></table>"
    )
    stats = (
        '<div class="perio-stats">'
        "<span>4mm以上 <b>6本</b> 前回 9本</span>"
        "<span>BOP <b>15%</b> 前回 19%</span>"
        "<span>PCR <b>18%</b> 前回 24%</span>"
        "<span>動揺のある歯 <b>0本</b> 前回 0本</span>"
        "<span>検査した歯 <b>26本</b></span></div>"
    )
    return card(
        "perio-exam", "歯周基本検査", stats + table, 12, extra="検査日 2026年8月7日", actions=FULL
    )


def _side():
    rows = "".join(f"<tr><td>{n}</td><td>{d}</td></tr>" for n, d in PURCHASES)
    interval = (
        '<div><div class="lbl">メンテナンス間隔</div>'
        '<div class="kv"><b>3か月ごと</b> 前回 2026年8月7日</div></div>'
    )
    hist = (
        '<div class="fill"><div class="lbl">使用ケア用品・購入履歴</div>'
        '<table class="t"><thead><tr><th>品名</th><th>最後に買った日</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )
    return card("", "", interval + hist, 3, cls="side-card")


def render():
    appt = "15:30〜16:00（30分）<small>前の予約 14:30〜15:30 RCT</small>"
    top = topbar(
        "歯科衛生士用",
        appt,
        [("change-patient", "患者様を変える"), ("change-role", "役割を変える")],
    )
    body = (
        '<main class="body hygienist">'
        + intraoral(6, "c6", 12)
        + spoken(3, ["右下奥の清掃を指導", "寝る前の歯間ブラシを継続"], "00:48")
        + _side()
        + _perio()
        + "</main>"
    )
    return page("hygienist", "歯科衛生士の画面（見本）", top, bands_three(), body)
