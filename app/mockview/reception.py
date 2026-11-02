from app.mockview.parts import FULL, band, card, important, page, topbar

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
    recent = "".join(f"<tr><td>{d}</td><td>{p}</td></tr>" for d, p in RECENT)
    inner = (
        '<div class="kv"><div>今回 <b>2026年11月6日 金曜日</b></div>'
        "<div>時間 <b>14:30〜16:00（1時間30分）</b></div></div>"
        '<div class="fill"><div class="lbl">最近の来院</div>'
        f'<table class="t"><tbody>{recent}</tbody></table></div>'
    )
    return card("", "予約日時", inner, 4)


def _heat():
    head = "".join(f'<th class="n">{d}</th>' for d in "月火水木金土")
    rows = "".join(
        f'<tr><th>{t}</th>'
        + "".join(f'<td class="n{" hot" if v >= 5 else ""}">{v}</td>' for v in vs)
        + "</tr>"
        for t, vs in HEAT
    )
    inner = (
        '<div class="big-num">金曜の午後</div>'
        f'<table class="t heat"><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table>'
    )
    return card("", "来院しやすい曜日・時間帯", inner, 5, extra="過去1年の来院13回")


def _cancel():
    inner = (
        '<div class="big-num">1回</div>'
        '<div class="kv">予約14回のうち 無断キャンセル 0回</div>'
        '<div><div class="lbl">キャンセルした日</div>'
        '<div class="kv">2026/3/12(木) 当日の朝に電話あり</div></div>'
    )
    return card("", "キャンセル傾向", inner, 3)


def _next():
    inner = (
        '<div><div class="lbl">今日</div>'
        '<div class="kv">右下第一大臼歯 RCT、SPT＋TBI</div></div>'
        '<div data-part="next-appointment"><div class="lbl">次回</div>'
        '<div class="next-big">支台築造＋形成印象'
        "<small>歯科医師 大川内 60分枠 2週間後ごろ</small></div></div>"
        '<div data-part="booked-appointment"><div class="lbl">予約済み</div>'
        '<div class="kv">2027年2月5日 歯科衛生士 田中 3か月SPT</div></div>'
    )
    return card("", "処置と次回の予約", inner, 4)


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
