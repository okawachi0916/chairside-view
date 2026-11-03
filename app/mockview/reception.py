from app.mockview.parts import FULL, band, card, important, page, topbar
from app.mockview.reception_parts import heat_card, next_card, reserve_card

RECENT = [
    ("2026年10月23日", "RCT"),
    ("2026年10月9日", "RCT"),
    ("2026年9月18日", "RCT"),
    ("2026年8月7日", "SPT"),
]
# 月〜土 の来院数。合計は13回
HEAT = [
    ("午前", [0, 0, 1, 0, 1, 0]),
    ("午後", [0, 1, 1, 0, 6, 1]),
    ("夕方", [0, 1, 0, 0, 0, 1]),
]
PURCHASES = [
    ("2026/9/18", "歯間ブラシ SS", "2"),
    ("2026/8/7", "フッ素ジェル", "1"),
    ("2026/8/7", "歯ブラシ やわらかめ", "1"),
    ("2026/5/8", "洗口液", "1"),
    ("2026/2/6", "デンタルフロス", "2"),
]
RX = [
    ("2026/10/9", "ロキソプロフェン錠 60mg", "6錠"),
    ("2026/9/18", "クラリスロマイシン錠 200mg", "6錠"),
    ("2026/9/18", "ロキソプロフェン錠 60mg", "6錠"),
]


def _reserve():
    return reserve_card(
        "2026年11月6日 金曜日", "14:30〜16:00（1時間30分）", [(d, p) for d, p in RECENT]
    )


def _heat():
    grid = [vs for _, vs in HEAT]
    return heat_card(grid, [t for t, _ in HEAT], "金曜の午後", 13)


def _cancel():
    inner = (
        '<div class="big-num">1回</div>'
        '<div class="kv">予約14回のうち 無断キャンセル 0回</div>'
        '<div><div class="lbl">キャンセルした日</div>'
        '<div class="kv">2026/3/12(木) 当日の朝に電話あり</div></div>'
    )
    return card("", "キャンセル傾向", inner, 3)


def _next():
    return next_card(
        "右下第一大臼歯 RCT、SPT＋TBI",
        "支台築造＋形成印象",
        ["歯科医師 大川内", "60分枠", "2週間後ごろ"],
        [("2027年2月5日", "歯科衛生士 佐藤 3か月SPT")],
    )


def _purchases():
    rows = "".join(
        f'<tr><td>{d}</td><td>{n}</td><td class="n">{c}</td></tr>' for d, n, c in PURCHASES
    )
    inner = (
        '<table class="t"><thead><tr><th>買った日</th><th>品名</th><th class="n">数</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )
    return card("", "過去の物品購入", inner, 3)


def _rx():
    rows = "".join(f"<tr><td>{d}</td><td>{n}</td><td>{q}</td></tr>" for d, n, q in RX)
    inner = (
        '<table class="t"><thead><tr><th>処方日</th><th>薬</th><th>量</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )
    return card("", "過去の処方", inner, 3)


def _back():
    inner = '<div class="card-back">次回のご予約 11月6日(金) 14:30</div>'
    return card("", "診察券 裏面", inner, 2)


def render():
    appt = "14:30〜15:30 RCT<small>15:30〜16:00 SPT</small>"
    top = topbar("受付用", appt, [("change-patient", "患者様を変える")], mic=False)
    memo = band("", "受付メモ", '<div class="big">お子さん3人と同じ時間で予約を取る</div>')
    bands = f'<div class="bands two">{important()}{memo}</div>'
    body = (
        '<main class="body reception">'
        + _reserve() + _heat() + _cancel()
        + _next() + _purchases() + _rx() + _back()
        + "</main>"
    )
    return page("reception", "受付の画面（見本）", top, bands, body)
