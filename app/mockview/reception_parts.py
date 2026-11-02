"""受付の画面の部品。見本（mockview/reception.py）と本物（views/render.py）で共通に使う。"""
from html import escape as h

from app.mockview.parts import card

WEEK6 = "月火水木金土"

# 時間帯の絵。太陽の高さで朝、昼、夕を表す
_SUN = {
    "午前": '<circle cx="16" cy="22" r="6"/><path d="M16 6v5M5 17l3.5 2M27 17l-3.5 2M3 27h26" />',
    "午後": '<circle cx="16" cy="16" r="6"/><path d="M16 2v5M16 25v5M2 16h5M25 16h5M6 6l3.5 3.5M22.5 22.5L26 26M26 6l-3.5 3.5M9.5 22.5L6 26"/>',
    "夕方": '<path d="M7 24a9 9 0 0 1 18 0"/><path d="M3 24h26M16 6v4M5 14l3 2M27 14l-3 2"/>',
}
_RANGE = {"午前": "〜12時", "午後": "12〜17時", "夕方": "17時〜"}


def _level(v):
    return 0 if v == 0 else 1 if v == 1 else 2 if v == 2 else 3 if v <= 4 else 4


def heat_card(grid, bands, big, total):
    """grid は 行=時間帯、列=月〜土 の来院数。数の多いほど濃い色にする。"""
    best = max((v, -b, -w) for b, row in enumerate(grid) for w, v in enumerate(row))
    head = '<div class="hc-corner"></div>' + "".join(
        f'<div class="hc-day">{d}</div>' for d in WEEK6
    )
    body = ""
    for b, name in enumerate(bands):
        icon = (
            f'<svg viewBox="0 0 32 32" aria-hidden="true" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round">{_SUN[name]}</svg>'
        )
        body += (
            f'<div class="hc-time">{icon}<span><b>{name}</b><small>{_RANGE[name]}</small></span></div>'
        )
        for w, v in enumerate(grid[b]):
            top = " top" if v and v == best[0] and (-best[1], -best[2]) == (b, w) else ""
            body += f'<div class="hc-cell l{_level(v)}{top}">{v}</div>'
    inner = (
        f'<div class="big-num">{h(big)}</div>'
        f'<div class="heat-cal">{head}{body}</div>'
    )
    return card("", "来院しやすい曜日・時間帯", inner, 5, extra=f"過去1年の来院{total}回")


def next_card(today_txt, next_body, next_chips, booked):
    """次回を一番大きく。担当医の名前、枠の長さ、時期も大きく出す。booked は (日付, 内容) の並び。"""
    chips = " ".join(f'<span class="chip">{h(c)}</span>' for c in next_chips)
    nxt = (
        f'<div class="next-main">{h(next_body)}</div><div class="chips">{chips}</div>'
        if next_body
        else '<div class="next-main none">―</div>'
    )
    bk = "".join(
        f'<div class="bk"><b>{h(d)}</b> <span>{h(t)}</span></div>' for d, t in booked
    ) or '<div class="bk"><span>―</span></div>'
    inner = (
        f'<div class="blk today"><span class="tag">今日</span><span class="today-txt">{h(today_txt)}</span></div>'
        f'<div class="blk next" data-part="next-appointment"><span class="tag big">次回</span>{nxt}</div>'
        f'<div class="blk booked" data-part="booked-appointment"><span class="tag">予約済み</span>'
        f'<div class="bks">{bk}</div></div>'
    )
    return card("", "処置と次回の予約", inner, 4, cls="next-card")


def reserve_card(date_txt, time_txt, recent):
    """今回の予約日時と、最近の来院。recent は (日付, 処置) の並び。"""
    rows = "".join(
        f'<div class="rv"><span class="d">{h(d)}</span><span class="p">{h(p)}</span></div>' for d, p in recent
    )
    inner = (
        f'<div class="when"><span class="lbl2">今回</span><b>{h(date_txt)}</b></div>'
        f'<div class="when"><span class="lbl2">時間</span><b>{h(time_txt)}</b></div>'
        f'<div class="lbl">最近の来院</div><div class="recent">{rows}</div>'
    )
    return card("", "予約日時", inner, 4, cls="reserve-card")
