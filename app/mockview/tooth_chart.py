"""歯の状態の絵。SVG で描く。見本（mockview/doctor.py）と本物（views/render.py）で共通に使う。

上顎と下顎を2行にし、歯冠どうしが咬み合うように向かい合わせる。
1本は「歯冠が上（咬む面が y=0）、根が下」の形で描き、上顎は上下を返して置く。
1本の歯の状態は「歯冠」「根」「カリエスの有無」の3つで持つ（G07f、G07g）。色は CSS の変数（.tc-* の決まり）。
見る場所は診療室の40インチのテレビ（1920×1080）。線・印・字は離れて見て分かる太さにする。"""
import re
from html import escape

# 見ている向きの左から右。上顎 18〜11 | 21〜28、下顎 48〜41 | 31〜38
UPPER = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
LOWER = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]

COL = 56  # 1本の幅
MID = 16  # 正中の空き
LEFT = 4
W = LEFT * 2 + COL * 16 + MID
NO_TOP = 28  # 上の歯番の字の下の線
LEN = 132  # 歯冠の先から根の先まで（G07g で少し短くし、同じ高さの枠で歯を大きく出す）
CROWN = 60  # 歯冠の高さ
UPPER_OCC = NO_TOP + 4 + LEN  # 上顎の咬む面
LOWER_OCC = UPPER_OCC + 8  # 下顎の咬む面
H = LOWER_OCC + LEN + 32

BODY = {1: 38, 2: 34, 3: 38, 4: 40, 5: 40, 6: 52, 7: 50, 8: 48}  # 歯の太さ
ROOTS = {"upper": {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3, 7: 3, 8: 3},
         "lower": {1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2}}

# 歯冠: 健全 / 充填（CR・インレー・充填）/ クラウン / ブリッジ支台 / 残根 / 欠損 / なし（インプラントで上部構造が無い）
# 根: 生活 / 失活 / 根治中 / 根充済 / インプラント
# カリエスは歯冠とは別の印（G07g）。健全・充填・クラウン・ブリッジ支台に重ねられる
CROWNS = ("健全", "CR", "インレー", "充填", "クラウン", "ブリッジ支台", "残根", "欠損", "なし")
ROOTS_STATE = ("生活", "失活", "根治中", "根充済", "インプラント")
MISSING = {"欠損"}
CAP = {"クラウン", "ブリッジ支台"}  # 歯冠を全部おおう（灰色）
PART = {"CR", "インレー", "充填"}  # 歯冠の一部を直す（緑）
IMPLANT = "インプラント"
CARIES = re.compile(r"^(カリエス|う蝕|C[1-4])$")
# 今までの1つの状態の文字を、歯冠と根に読み替える。ここに無い文字は歯冠の状態として読む
OLD = {
    "欠損": ("欠損", ""),
    "RCT中": ("健全", "根治中"),
    "根管治療済": ("健全", "根充済"),
    "失活": ("健全", "失活"),
    "残根": ("残根", "失活"),
}
WAIT = re.compile(r"経過観察|様子を見")  # 計画にあっても処置ではない

_Q = {"右上": 1, "左上": 2, "左下": 3, "右下": 4}


def parts(v):
    """歯の状態を (歯冠, 根, カリエス) にする。
    v は (歯冠, 根)、(歯冠, 根, カリエス)、今までの1つの状態の文字のどれか。
    歯冠の文字に「+カリエス」や「C2」が入っていれば、カリエスの印として読み替える。"""
    caries = False
    if isinstance(v, (tuple, list)):
        crown, root = (v[0] or "健全"), (v[1] or "")
        caries = bool(v[2]) if len(v) > 2 else False
    else:
        v = (v or "").strip()
        crown, root = OLD.get(v, (v or "健全", ""))
    words = [w for w in crown.split("+") if w]
    caries = caries or any(CARIES.match(w) for w in words)
    crown = "+".join(w for w in words if not CARIES.match(w)) or "健全"
    if crown in MISSING:
        return "欠損", "", False
    if root == IMPLANT:  # 上部構造があれば冠（灰色）、無ければ冠を描かない
        return ("クラウン" if set(crown.split("+")) & CAP else "なし"), IMPLANT, False
    if "残根" in crown.split("+"):
        return "残根", ("根充済" if root == "根充済" else "失活"), caries  # 残根に生活歯はない
    return crown, (root or "生活"), caries


def marks(crown):
    m = set(crown.split("+"))
    return {"cap": bool(m & CAP), "fill": bool(m & PART), "root_only": "残根" in m, "no_crown": "なし" in m}


def describe(v, pontic=False):
    """1本の歯の状態を文字にする（絵の中の説明、ほかの画面で文字で出すとき）。"""
    if pontic:
        return "ブリッジのポンティック"
    crown, root, caries = parts(v)
    if crown in MISSING:
        return "欠損"
    if root == IMPLANT:
        return "インプラント（上部構造あり）" if crown == "クラウン" else "インプラント（上部構造なし）"
    name = "・".join(crown.split("+"))
    if caries:
        name = "カリエス" if crown == "健全" else f"{name}＋カリエス"
    return f"{name}、{root}" if root != "生活" else (name if crown != "健全" or caries else "健全")


def treated(v):
    """処置した歯（充填・クラウン・ブリッジ・根の治療・インプラント）。カリエスだけ・残根だけは処置ではない。"""
    crown, root, _ = parts(v)
    m = marks(crown)
    return m["cap"] or m["fill"] or root in ("根治中", "根充済", IMPLANT)


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


_TOOTH_MENTION = re.compile(r"(?:右上|左上|左下|右下)\s*[1-8]\s*番")


def today_teeth(texts):
    """今日の処置の文（予約の予定「右下6番 根管充填」、記録した「やったこと」の「右下6番の根管充填、左上3番のCR充填」など）から、
    1本に決まる歯だけを取り出す。1つの文に歯が何本も出てくるときは、出てきた歯を全部（G19m）。"""
    out = set()
    for x in texts:
        mentions = _TOOTH_MENTION.findall(x or "")
        for m in mentions:
            out |= site_teeth(m)
        if not mentions:
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
    """根管。失活は黒い線、根治中はオレンジの枠（中は白）、根充済はオレンジの塗り。生活は描かない。"""
    if root == "失活":
        return "".join(f'<path class="tc-canal dead" d="M {c:.1f},{top} L {c:.1f},{LEN - 12}"/>' for c in centers)
    if root not in ("根治中", "根充済"):
        return ""
    cls = "tc-canal filled" if root == "根充済" else "tc-canal open"
    return "".join(
        f'<path class="{cls}" d="M {c - 4.5:.1f},{top} L {c - 1.5:.1f},{LEN - 12} L {c + 1.5:.1f},{LEN - 12} '
        f'L {c + 4.5:.1f},{top} Z"/>'
        for c in centers
    )


def _implant(cx, bw):
    """インプラントのフィクスチャー（ねじ）。根の所に先の細い台形を描き、ねじ山を斜線で入れる。"""
    top, bot = CROWN + 4, LEN - 6
    t, b = bw * 0.30, bw * 0.19  # 上と下の半分の幅
    out = (f'<path class="tc-fixture" d="M {cx - t:.1f},{top} L {cx - b:.1f},{bot} Q {cx:.1f},{bot + 6} '
           f'{cx + b:.1f},{bot} L {cx + t:.1f},{top} Z"/>')
    # 冠とつなぐ首（アバットメント）
    out += f'<rect class="tc-fixture" x="{cx - t * 0.6:.1f}" y="{CROWN - 6}" width="{t * 1.2:.1f}" height="10"/>'
    y = top + 10
    while y + 10 < bot:
        k0, k1 = (y + 10 - top) / (bot - top), (y - top) / (bot - top)
        w0, w1 = t - (t - b) * k0, t - (t - b) * k1  # その高さでの半分の幅
        out += f'<path class="tc-thread" d="M {cx - w0 + 1:.1f},{y + 10:.1f} L {cx + w1 - 1:.1f},{y:.1f}"/>'
        y += 11
    return out


def _tooth(cx, n, jaw, status):
    """1本の歯（歯冠の先が y=0）。status は parts で読める形。"""
    crown, root, caries = parts(status)
    m = marks(crown)
    bw = BODY[n]
    hw = bw / 2
    if root == IMPLANT:
        out = _implant(cx, bw)
        if m["cap"]:  # 上部構造
            out += f'<path class="tc-crown cap" d="{_crown_path(cx, bw, n)}"/>'
        return out
    roots, centers = _roots(cx, bw, ROOTS[jaw][n])
    out = roots + _canals(centers, root, CROWN + 2)
    if m["root_only"]:  # 残根: 歯冠は描かず、根だけ
        return out
    out += f'<path class="{"tc-crown cap" if m["cap"] else "tc-crown"}" d="{_crown_path(cx, bw, n)}"/>'
    if m["fill"] and not m["cap"]:
        out += f'<ellipse class="tc-fill" cx="{cx:.1f}" cy="16" rx="{hw * 0.62:.1f}" ry="10"/>'
    if caries:  # 充填の横、冠の上にも重ねる
        out += (f'<circle class="tc-caries" cx="{cx + (hw * 0.42 if m["fill"] else 0):.1f}" '
                f'cy="{40 if m["fill"] else 32}" r="7.5"/>')
    return out


def _pontic(cx, n):
    """ブリッジのダミーの歯。灰色の冠だけで、根は描かない。"""
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
        f'<rect class="tc-box {boxes[t]}" data-tooth="{t}" x="{_x(i) - COL / 2 + 3:.1f}" y="-5" width="{COL - 6}" '
        f'height="{LEN + 8}" rx="6"/>'
        for i, t in enumerate(order) if t in boxes
    )
    # ブリッジ: 冠と冠の間に灰色の棒を渡し、つながって見せる（棒の高さは冠より少し低い。冠の下に敷く）
    for a, b in spans:
        body += (f'<rect class="tc-crown cap tc-bridge" x="{_x(a):.1f}" y="14" width="{_x(b) - _x(a):.1f}" '
                 f'height="{CROWN - 24}"/>')
    for i, t in enumerate(order):
        if i in pontics:
            body += (f'<g class="tc-tooth pontic" data-tooth="{t}"><title>{t} {describe("", pontic=True)}</title>'
                     f'{_pontic(_x(i), t % 10)}</g>')
        elif not _gone(status, t):
            v = status.get(t, "")
            crown, root, caries = parts(v)
            body += (f'<g class="tc-tooth" data-tooth="{t}" data-crown="{crown}" data-root="{root}" '
                     f'data-caries="{int(caries)}"><title>{t} {escape(describe(v))}</title>'
                     f'{_tooth(_x(i), t % 10, jaw, v)}</g>')
    return f'<g class="tc-jaw tc-{jaw}" transform="{flip}">{body}</g>'


def _numbers(order, y, status):
    return "".join(
        f'<text class="{"tc-no gone" if _gone(status, t) else "tc-no"}" x="{_x(i):.1f}" y="{y}" data-no="{t}">{t % 10}</text>'
        for i, t in enumerate(order)
    )


def chart_svg(status, own=(), today=(), doing=()):
    """status: 歯番 → parts で読める状態（無い歯は「欠損」）。
    own: 自院で治療が済んだ歯（点線の四角）。doing: 自院で治療の途中の歯（濃い四角）。
    today: 今日の処置の歯。左上の「今日の処置」の欄に出ているので、治療済みの四角は付けない
    （治療の途中の歯は、今日の処置の歯でも濃い四角で囲む。院長の決定 11/4）。"""
    boxes = {t: "done" for t in set(own) - set(today)}
    boxes.update({t: "doing" for t in doing})
    mid = LEFT + COL * 8 + MID / 2
    return (
        f'<svg class="tooth-svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMaxYMid meet" role="img" aria-label="歯の状態">'
        f'<line class="tc-mid" x1="{mid}" y1="6" x2="{mid}" y2="{H - 6}"/>'
        + _jaw(UPPER, "upper", status, boxes)
        + _jaw(LOWER, "lower", status, boxes)
        + _numbers(UPPER, NO_TOP - 2, status)
        + _numbers(LOWER, H - 4, status)
        + "</svg>"
    )


# 色と形の説明。絵の左に縦に並べる（G07g。字の大きさと太さはそろえる）
LEGEND = (
    '<div class="tc-legend">'
    '<div><span><i class="sw"></i>健全</span><span><i class="sw fill"></i>充填</span>'
    '<span><i class="dot"></i>カリエス</span></div>'
    '<div><span><i class="sw cap"></i>クラウン・ブリッジ</span></div>'
    '<div class="cn-row"><span class="cn-lbl">根管</span><span><i class="cn dead"></i>失活</span>'
    '<span><i class="cn open"></i>根治中</span><span><i class="cn filled"></i>根充済</span></div>'
    '<div><span><i class="imp"></i>インプラント</span></div>'
    '<div class="gap"><span><i class="bx done"></i>自院で治療済み</span>'
    '<span><i class="bx doing"></i>自院で治療中</span></div>'
    "</div>"
)


def is_denture(kind):
    """有床義歯（部分床義歯・総義歯）か。ブリッジは有床義歯ではない。"""
    return "義歯" in (kind or "")


def is_own(made_by):
    return any(w in (made_by or "") for w in ("当院", "自院"))


def _group(rows):
    """種類・作成元・作った日が同じものは1行にまとめ、場所を「・」でつなぐ（上顎・下顎 総義歯 など）。"""
    out = {}
    for x in rows:
        key = (x.get("kind"), x.get("made_by"), x.get("date"))
        if key in out:
            out[key]["site"] += "・" + (x.get("site") or "")
        else:
            out[key] = dict(x)
    return list(out.values())


def appliance_html(dentures, mucosal=()):
    """歯の絵の外に出す、有床義歯の あり／なし と作成元、ブリッジの作成元、その他粘膜疾患。
    dentures: site, kind, made_by, date（画面に出す作った日の文字。無ければ空）を持つ辞書の並び。
    データの「当院作成」は画面では「自院作成」と出す。"""
    dent = _group([x for x in dentures if is_denture(x.get("kind"))])
    other = _group([x for x in dentures if not is_denture(x.get("kind"))])

    def made(x):
        if is_own(x.get("made_by")):
            date = f'<span class="tc-date">{escape(x.get("date") or "")}</span>' if x.get("date") else ""
            return f'<span class="tc-tag own">自院作成</span>{date}'
        if "他院" in (x.get("made_by") or ""):
            return '<span class="tc-tag other">他院作成</span>'
        return ""

    def row(x):
        return (f'<div class="tc-dent-row"><span class="tc-dent-what">{escape(x.get("site") or "")} '
                f'{escape(x.get("kind") or "")}</span>{made(x)}</div>')

    head = ('<div class="tc-dent-head"><b>有床義歯</b>'
            + ('<span class="tc-has yes">あり</span>' if dent else '<span class="tc-has no">なし</span>') + "</div>")
    out = f'<div class="tc-dent{" yes" if dent else " no"}">{head}{"".join(row(x) for x in dent)}</div>'
    if other:
        out += '<div class="tc-dent other">' + "".join(row(x) for x in other) + "</div>"
    for m in mucosal:
        out += (f'<div class="tc-muc"><b>その他粘膜疾患</b> <span>{escape(m.get("site") or "")} '
                f'{escape(m.get("name") or "")}</span></div>')
    return out


def panel(svg, dentures, mucosal=()):
    """「歯の状態」の中身。左に凡例と義歯・粘膜の表示、右に大きな歯の絵。"""
    return (f'<div class="teeth"><div class="frame"><div class="tc-left">{LEGEND}'
            f'<div class="tc-notes">{appliance_html(dentures, mucosal)}</div></div>{svg}</div></div>')
