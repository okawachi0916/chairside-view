"""歯の状態の絵。SVG で描く。見本（mockview/doctor.py）と本物（views/render.py）で共通に使う。

上顎と下顎を2行にし、歯冠どうしが咬み合うように向かい合わせる。
1本は「歯冠が上（咬む面が y=0）、根が下」の形で描き、上顎は上下を返して置く。
1本の歯の状態は「歯冠」と「根」の2つで持つ（G07f）。色は CSS の変数（.tc-* の決まり）。"""
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

# 歯冠: 健全 / カリエス / 充填（CR・インレー・充填）/ クラウン / ブリッジ支台 / 残根 / 欠損。
# 「インレー+カリエス」のように + でつないでよい（二次カリエス）。根: 生活 / 失活 / 根治中 / 根充後
CROWNS = ("健全", "カリエス", "CR", "インレー", "充填", "クラウン", "ブリッジ支台", "残根", "欠損")
ROOTS_STATE = ("生活", "失活", "根治中", "根充後")
MISSING = {"欠損"}
CAP = {"クラウン", "ブリッジ支台"}  # 歯冠を全部おおう（灰色）
PART = {"CR", "インレー", "充填"}  # 歯冠の一部を直す（緑）
CARIES = re.compile(r"カリエス|う蝕|C[1-4]")
# 今までの1つの状態の文字を、歯冠と根に読み替える。ここに無い文字は歯冠の状態として読む
OLD = {
    "欠損": ("欠損", ""),
    "RCT中": ("健全", "根治中"),
    "根管治療済": ("健全", "根充後"),
    "失活": ("健全", "失活"),
    "残根": ("残根", "失活"),
}
WAIT = re.compile(r"経過観察|様子を見")  # 計画にあっても処置ではない

_Q = {"右上": 1, "左上": 2, "左下": 3, "右下": 4}


def parts(v):
    """歯の状態を (歯冠, 根) にする。v は (歯冠, 根) か、今までの1つの状態の文字。"""
    if isinstance(v, (tuple, list)):
        crown, root = (v[0] or "健全"), (v[1] or "")
    else:
        v = (v or "").strip()
        crown, root = OLD.get(v, (v or "健全", ""))
    if crown in MISSING:
        return "欠損", ""
    if "残根" in crown.split("+"):
        return "残根", ("根充後" if root == "根充後" else "失活")  # 残根に生活歯はない
    return crown, (root or "生活")


def marks(crown):
    m = set(crown.split("+"))
    return {"cap": bool(m & CAP), "fill": bool(m & PART), "caries": bool(CARIES.search(crown)),
            "root_only": "残根" in m}


def treated(v):
    """処置した歯（充填・クラウン・ブリッジ・根の治療）。カリエスだけ・残根だけは処置ではない。"""
    crown, root = parts(v)
    m = marks(crown)
    return m["cap"] or m["fill"] or root in ("根治中", "根充後")


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
    治療歴に1本の歯として出てくる歯は自院。どちらにも無い処置済みの歯は自院とみなさない。"""
    other = set()
    for x in dentures:
        if "他院" in (x.get("made_by") or ""):
            other |= site_teeth(x.get("site"))
    mine = set()
    for s in history_sites:
        t = site_teeth(s)
        if len(t) == 1:
            mine |= t
    return {t for t, s in status.items() if treated(s) and t in mine and t not in other}


def doing_teeth(status, plans):
    """自院で治療の途中の歯: 根治中の歯と、今の治療計画に1本に決まる処置がある歯（経過観察は除く）。"""
    out = {t for t, s in status.items() if parts(s)[1] == "根治中"}
    for body in plans:
        t = site_teeth(body)
        if len(t) == 1 and not WAIT.search(body or ""):
            out |= {x for x in t if parts(status.get(x, ""))[0] not in MISSING}
    return out


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
    return roots, centers


def _canals(centers, root, top):
    """根管。失活は黒い線、根治中はオレンジの枠（中は白）、根充後はオレンジの塗り。生活は描かない。"""
    if root == "失活":
        return "".join(f'<path class="tc-canal dead" d="M {c:.1f},{top} L {c:.1f},{LEN - 12}"/>' for c in centers)
    if root not in ("根治中", "根充後"):
        return ""
    cls = "tc-canal filled" if root == "根充後" else "tc-canal open"
    return "".join(
        f'<path class="{cls}" d="M {c - 4:.1f},{top} L {c - 1.5:.1f},{LEN - 12} L {c + 1.5:.1f},{LEN - 12} '
        f'L {c + 4:.1f},{top} Z"/>'
        for c in centers
    )


def _tooth(cx, n, jaw, status):
    """1本の歯（歯冠の先が y=0）。status は (歯冠, 根) か今までの状態の文字。"""
    crown, root = parts(status)
    m = marks(crown)
    bw = BODY[n]
    hw = bw / 2
    roots, centers = _roots(cx, bw, ROOTS[jaw][n])
    if m["root_only"]:  # 残根: 歯冠は描かず、根だけ
        return roots + _canals(centers, root, CROWN + 2)
    out = roots + _canals(centers, root, CROWN + 2)
    out += f'<path class="{"tc-crown cap" if m["cap"] else "tc-crown"}" d="{_crown_path(cx, bw, n)}"/>'
    if m["fill"] and not m["cap"]:
        out += f'<ellipse class="tc-fill" cx="{cx:.1f}" cy="14" rx="{hw * 0.6:.1f}" ry="9"/>'
    if m["caries"]:
        out += f'<circle class="tc-caries" cx="{cx + (hw * 0.4 if m["fill"] else 0):.1f}" cy="{36 if m["fill"] else 28}" r="6"/>'
    return out


def _pontic(cx, n):
    return f'<path class="tc-crown cap" d="{_crown_path(cx, BODY[n], n)}"/>'


def _gone(status, t):
    return parts(status.get(t, ""))[0] in MISSING


def _bridges(order, status):
    """支台の間が欠損でつながっていれば、ブリッジの範囲 (始め, 終わり) の並びを返す（列の番号）。"""
    spans = []
    abut = [i for i, t in enumerate(order) if "ブリッジ支台" in parts(status.get(t, ""))[0].split("+")]
    for a, b in zip(abut, abut[1:]):
        between = order[a + 1:b]
        if between and all(_gone(status, t) for t in between):
            spans.append((a, b))
    return spans


def _jaw(order, jaw, status, boxes):
    occ = UPPER_OCC if jaw == "upper" else LOWER_OCC
    flip = f"translate(0,{occ}) scale(1,-1)" if jaw == "upper" else f"translate(0,{occ})"
    spans = _bridges(order, status)
    pontics = {i for a, b in spans for i in range(a + 1, b)}
    # 囲みは歯より先に描き、歯の下に敷く
    body = "".join(
        f'<rect class="tc-box {boxes[t]}" data-tooth="{t}" x="{_x(i) - COL / 2 + 2:.1f}" y="-6" width="{COL - 4}" '
        f'height="{LEN + 12}" rx="6"/>'
        for i, t in enumerate(order) if t in boxes
    )
    for a, b in spans:
        body += f'<rect class="tc-crown cap tc-bridge" x="{_x(a):.1f}" y="20" width="{_x(b) - _x(a):.1f}" height="24" rx="4"/>'
    for i, t in enumerate(order):
        if i in pontics:
            body += f'<g class="tc-tooth pontic" data-tooth="{t}">{_pontic(_x(i), t % 10)}</g>'
        elif not _gone(status, t):
            crown, root = parts(status.get(t, ""))
            body += (f'<g class="tc-tooth" data-tooth="{t}" data-crown="{crown}" data-root="{root}">'
                     f'{_tooth(_x(i), t % 10, jaw, status.get(t, ""))}</g>')
    return f'<g class="tc-jaw tc-{jaw}" transform="{flip}">{body}</g>'


def _numbers(order, y, status):
    return "".join(
        f'<text class="{"tc-no gone" if _gone(status, t) else "tc-no"}" x="{_x(i):.1f}" y="{y}" data-no="{t}">{t % 10}</text>'
        for i, t in enumerate(order)
    )


def chart_svg(status, own=(), today=(), doing=()):
    """status: 歯番 → (歯冠, 根) か今までの状態の文字（無い歯は「欠損」）。
    own: 自院で治療が済んだ歯（薄い四角）。doing: 自院で治療の途中の歯（濃い四角）。
    today: 今日の処置の歯。左上の「今日の処置」の欄に出ているので、治療済みの薄い四角は付けない
    （治療の途中の歯は、今日の処置の歯でも濃い四角で囲む。院長の決定 11/4）。"""
    boxes = {t: "done" for t in set(own) - set(today)}
    boxes.update({t: "doing" for t in doing})
    mid = LEFT + COL * 8 + MID / 2
    return (
        f'<svg class="tooth-svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="歯の状態">'
        f'<line class="tc-mid" x1="{mid}" y1="8" x2="{mid}" y2="{H - 8}"/>'
        + _jaw(UPPER, "upper", status, boxes)
        + _jaw(LOWER, "lower", status, boxes)
        + _numbers(UPPER, 18, status)
        + _numbers(LOWER, H - 4, status)
        + "</svg>"
    )


# 色の説明。絵の下に1行で置く
LEGEND = (
    '<div class="tc-legend">'
    '<span><i class="sw"></i>健全</span><span><i class="sw fill"></i>充填</span>'
    '<span><i class="sw cap"></i>クラウン・ブリッジ</span><span><i class="dot"></i>カリエス</span>'
    '<span class="grp lbl">根管</span><span><i class="cn dead"></i>失活</span><span><i class="cn open"></i>根治中</span>'
    '<span><i class="cn filled"></i>根充後</span>'
    '<span class="grp"><i class="bx done"></i>自院で治療済み</span><span><i class="bx doing"></i>自院で治療中</span>'
    "</div>"
)
