from app.mockview.parts import bands_three, card, intraoral, page, spoken, topbar
from app.mockview.perio_parts import perio_card

PURCHASES = [
    ("歯間ブラシ SS", "2026/9/18"),
    ("フッ素ジェル", "2026/8/7"),
    ("歯ブラシ やわらかめ", "2026/8/7"),
    ("洗口液", "2026/5/8"),
    ("デンタルフロス", "2026/2/6"),
]

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


def _teeth():
    out = {}
    for t in POCKET:
        out[t] = {
            "pocket": POCKET[t],
            "bop": t in BOP,
            "mobility": LOOSE.get(t, 0),
            "sides": set(PLAQUE.get(t, "")),
        }
    return out


def _perio():
    stats = [
        ("4mm以上", "6本", "9本"),
        ("BOP", "15%", "19%"),
        ("PCR", "18%", "24%"),
        ("動揺のある歯", "0本", "0本"),
        ("検査した歯", "26本", None),
    ]
    return perio_card(_teeth(), stats, "2026年8月7日")


def _side():
    rows = "".join(f"<tr><td>{n}</td><td>{d}</td></tr>" for n, d in PURCHASES)
    interval = card(
        "", "メンテナンス間隔",
        '<div class="kv"><b>3か月ごと</b> <span class="prev">前回 2026年8月7日</span></div>', None,
    )
    hist = card(
        "", "使用ケア用品・購入履歴",
        '<table class="t"><thead><tr><th>品名</th><th>最後に買った日</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>", None,
    )
    return f'<div class="stack" style="grid-column: span 3">{interval}{hist}</div>'


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
