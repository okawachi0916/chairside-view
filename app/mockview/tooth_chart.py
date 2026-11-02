"""歯の状態の絵。SVG で描く。見本（mockview/doctor.py）と本物（views/render.py）で共通に使う。

上顎と下顎を2行にし、歯冠どうしが咬み合うように向かい合わせる。
1本は「歯冠が上（咬む面が y=0）、根が下」の形で描き、上顎は上下を返して置く。
色は CSS の変数（.tc-* の決まり）。"""
import re

# 見ている向きの左から右。上顎 18〜11 | 21〜28、下顎 48〜41 | 31〜38
UPPER = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
LOWER = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]

COL = 56  # 1本の幅
MID = 16  # 正中の空き
LEFT = 8
W = LEFT * 2 + COL * 16 + MID
UPPER_OCC = 176  # 上顎の咬む面
LOWER_OCC = 184  # 下顎の咬む面
LEN = 148  # 歯冠の先から根の先まで
CROWN = 64  # 歯冠の高さ
H = LOWER_OCC + LEN + 30

BODY = {1: 38, 2: 34, 3: 38, 4: 40, 5: 40, 6: 52, 7: 50, 8: 48}  # 歯の太さ
ROOTS = {"upper": {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3, 7: 3, 8: 3},
         "lower": {1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2}}

MISSING = {"欠損"}
DEAD = {"RCT中", "根管治療済", "残根", "失活"}  # 歯髄を取った歯
CAP = {"クラウン", "ブリッジ支台"}  # 歯冠を全部おおう
PART = {"CR", "インレー", "充填"}  # 歯冠の一部を直す
ROOT_ONLY = {"残根"}
TREATED = (DEAD - ROOT_ONLY) | CAP | PART  # 処置した歯。残根は処置ではない

_Q = {"右上": 1, "左上": 2, "左下": 3, "右下": 4}


def site_teeth(site):
    """「右下6番」「下顎」「上顎左側」などを歯番の集まりにする。分からなければ空。"""
    site = site or ""
    m = re.search(r"(右上|左上|左下|右下)\s*([1-8])番", site)
    if m:
        return {_Q[m.group(1)] * 10 + int(m.group(2))}
    quads = set()
    if "上顎" in site:
        quads |= {1, 2}
    if "下顎" in site:
        quads |= {3, 4}
    if "右側" in site:
        quads &= {1, 4}
    if "左側" in site:
        quads &= {2, 3}
    if "全顎" in site:
        quads = {1, 2, 3, 4}
    return {q * 10 + n for q in quads for n in range(1, 9)}


def today_teeth(texts):
    """今日の処置の文（「右下6番 根管充填」など）から、1本に決まる歯だけを取り出す。"""
    out = set()
    for x in texts:
        t = site_teeth(x)
        if len(t) == 1:
            out |= t
    return out


def own_teeth(status, history_sites, dentures):
    """自院で処置した歯。義歯やブリッジの記録が他院ならその範囲は他院。
    治療歴に1本の歯として出てくる歯は自院。どちらにも無い処置済みの歯は他院とみなす。"""
    other = set()
    for x in dentures:
        if "他院" in (x.get("made_by") or ""):
            other |= site_teeth(x.get("site"))
    mine = set()
    for s in history_sites:
        t = site_teeth(s)
        if len(t) == 1:
            mine |= t
    return {t for t, s in status.items() if s in TREATED and t in mine and t not in other}


def _x(i):
    return LEFT + i * COL + (MID if i >= 8 else 0) + COL / 2


def _crown_path(cx, bw, n):
    hw = bw / 2
    x0, x1 = cx - hw, cx + hw
    if n >= 6:  # 山2つ
        top = f"Q {x0 + hw * 0.5:.1f},-6 {cx:.1f},6 Q {x1 - hw * 0.5:.1f},-6 {x1:.1f},16"
        start = f"M {x0 + 4:.1f},{CROWN} L {x0:.1f},16 "
    else:  # 山1つ
        top = f"Q {cx - hw * 0.5:.1f},-2 {cx:.1f},0 Q {cx + hw * 0.5:.1f},-2 {x1:.1f},18"
        start = f"M {x0 + 4:.1f},{CROWN} L {x0:.1f},18 "
    return f"{start}{top} L {x1 - 4:.1f},{CROWN} Z"


def _roots(cx, bw, k):
    rw = (bw - 8) / k if k > 1 else bw - 12
    step = (bw - 8 - rw) / (k - 1) if k > 1 else 0
    centers = [cx - (bw - 8 - rw) / 2 + step * i for i in range(k)]
    roots = "".join(
        f'<path class="tc-root" d="M {c - rw / 2:.1f},{CROWN - 2} L {c - 2:.1f},{LEN - 2} Q {c:.1f},{LEN + 2} '
        f'{c + 2:.1f},{LEN - 2} L {c + rw / 2:.1f},{CROWN - 2} Z"/>'
        for c in centers
    )
    canals = "".join(
        f'<path d="M {c - 2:.1f},{CROWN - 2} L {c - 0.6:.1f},{LEN - 12} L {c + 0.6:.1f},{LEN - 12} L {c + 2:.1f},{CROWN - 2} Z"/>'
        for c in centers
    )
    return roots, canals


def _tooth(cx, n, jaw, status):
    """1本の歯（歯冠の先が y=0）。status は歯の状態の文字。"""
    bw = BODY[n]
    hw = bw / 2
    roots, canals = _roots(cx, bw, ROOTS[jaw][n])
    pulp_cls = "tc-pulp dead" if status in DEAD else "tc-pulp"
    chamber = f'<rect x="{cx - hw * 0.4:.1f}" y="{CROWN - 30}" width="{hw * 0.8:.1f}" height="30" rx="6"/>'
    out = roots
    if status not in ROOT_ONLY:
        crown_cls = "tc-crown cap" if status in CAP else "tc-crown"
        out += f'<path class="{crown_cls}" d="{_crown_path(cx, bw, n)}"/>'
        if status in PART:
            out += f'<ellipse class="tc-fill" cx="{cx:.1f}" cy="13" rx="{hw * 0.6:.1f}" ry="9"/>'
        out += f'<g class="{pulp_cls}">{chamber}{canals}</g>'
    else:
        out += f'<g class="{pulp_cls}">{canals}</g>'
    return out


def _pontic(cx, n):
    return f'<path class="tc-crown cap" d="{_crown_path(cx, BODY[n], n)}"/>'


def _bridges(order, status):
    """支台の間が欠損でつながっていれば、ブリッジの範囲 (始め, 終わり) の並びを返す（列の番号）。"""
    spans = []
    abut = [i for i, t in enumerate(order) if status.get(t) == "ブリッジ支台"]
    for a, b in zip(abut, abut[1:]):
        between = order[a + 1:b]
        if between and all(status.get(t) in MISSING for t in between):
            spans.append((a, b))
    return spans


def _jaw(order, jaw, status, today):
    occ = UPPER_OCC if jaw == "upper" else LOWER_OCC
    flip = f"translate(0,{occ}) scale(1,-1)" if jaw == "upper" else f"translate(0,{occ})"
    spans = _bridges(order, status)
    pontics = {i for a, b in spans for i in range(a + 1, b)}
    body = ""
    for a, b in spans:
        body += f'<rect class="tc-crown cap tc-bridge" x="{_x(a):.1f}" y="20" width="{_x(b) - _x(a):.1f}" height="24" rx="4"/>'
    for i, t in enumerate(order):
        s = status.get(t, "")
        if i in pontics:
            body += f'<g class="tc-tooth pontic" data-tooth="{t}">{_pontic(_x(i), t % 10)}</g>'
        elif s not in MISSING:
            body += f'<g class="tc-tooth" data-tooth="{t}">{_tooth(_x(i), t % 10, jaw, s)}</g>'
    frames = "".join(
        f'<rect class="tc-today" data-tooth="{t}" x="{_x(i) - COL / 2 + 2:.1f}" y="-6" width="{COL - 4}" height="{LEN + 12}" rx="8"/>'
        for i, t in enumerate(order) if t in today
    )
    return f'<g class="tc-jaw tc-{jaw}" transform="{flip}">{body}{frames}</g>'


def _numbers(order, y, own, status):
    out = ""
    for i, t in enumerate(order):
        s = status.get(t, "")
        if s in MISSING:
            cls = "tc-no gone"
        elif s in TREATED:
            cls = "tc-no own" if t in own else "tc-no other"
        else:
            cls = "tc-no"
        out += f'<text class="{cls}" x="{_x(i):.1f}" y="{y}" data-no="{t}">{t % 10}</text>'
    return out


def chart_svg(status, own=(), today=()):
    """status: 歯番 → 状態の文字（無い歯は「欠損」）。own: 自院の歯。today: 今日の処置の歯。"""
    own, today = set(own), set(today)
    mid = LEFT + COL * 8 + MID / 2
    return (
        f'<svg class="tooth-svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="歯の状態">'
        f'<line class="tc-mid" x1="{mid}" y1="8" x2="{mid}" y2="{H - 8}"/>'
        + _jaw(UPPER, "upper", status, today)
        + _jaw(LOWER, "lower", status, today)
        + _numbers(UPPER, 18, own, status)
        + _numbers(LOWER, H - 4, own, status)
        + "</svg>"
    )


# 歯番の色の見分け
LEGEND = '<div class="tc-legend"><span class="own">自院</span><span class="other">他院</span></div>'
