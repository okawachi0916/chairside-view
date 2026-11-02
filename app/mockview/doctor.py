from app.mockview.parts import FULL, bands_three, card, intraoral, page, spoken, topbar

NOTES = [
    ("2026年10月23日", "右下6番 根管貼薬、仮封、打診痛なし。症状がなければ次回根管充填", False),
    ("2026年10月9日", "右下6番 抜髄、貼薬。次回は症状を確かめて貼薬交換", False),
    ("2026年9月18日", "右下6番 C3と診断、デンタル撮影。次回抜髄", False),
    ("2026年8月7日", "歯科衛生士 SPT、歯周検査", True),
    ("2026年7月15日", "左下7番 コンポジットレジン充填", False),
    ("2026年6月20日", "左下7番 C2と診断。次回充填", False),
    ("2026年5月8日", "歯科衛生士 SPT", True),
    ("2026年4月14日", "右上5番 知覚過敏の処置", False),
]

HISTORY = [
    ("2026/10/23", "右下6番", "根管貼薬、仮封"),
    ("2026/10/9", "右下6番", "抜髄、貼薬"),
    ("2026/9/18", "右下6番", "デンタル撮影"),
    ("2026/8/7", "全顎", "SPT、歯周検査"),
    ("2026/7/15", "左下7番", "CR充填"),
    ("2026/6/20", "左下7番", "C2の診断"),
    ("2026/5/8", "全顎", "SPT、義歯の作成"),
    ("2026/4/14", "右上5番", "知覚過敏の処置"),
    ("2026/2/6", "全顎", "SPT、歯周検査"),
    ("2025/11/14", "右上6番", "クラウン装着"),
]


def _today():
    notes = "".join(
        f'<div class="n{" hyg" if h else ""}">{d} {t}</div>' for d, t, h in NOTES
    )
    inner = (
        '<div class="today">'
        '<div class="main">右下6番 根管充填</div><div class="sub">根管治療 3回目</div></div>'
        '<div class="plan" data-part="treatment-plan"><h3>治療計画</h3>'
        "<div>右下6番 次回 支台築造と形成、そのあとクラウン</div>"
        "<div>左下7番 3か月様子を見る</div>"
        "<div>その間に 右上5番 の充填</div></div>"
        '<h3 class="notes-h">過去の診療メモ</h3>'
        f'<div class="notes" data-part="past-notes">{notes}</div>'
    )
    return card("today-treatment", "今日の処置", inner, 4, actions=FULL)


def _history():
    rows = "".join(
        f"<tr><td>{d}</td><td>{s}</td><td>{c}</td></tr>" for d, s, c in HISTORY
    )
    inner = (
        '<table class="t"><thead><tr><th>日付</th><th>部位</th><th>内容</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )
    return card("treatment-history", "治療歴", inner, 3, actions=FULL)


def _teeth():
    side = (
        '<div class="side">'
        "<div><b>その他粘膜疾患</b> <span>舌左縁 白板症</span></div>"
        "<div><b>義歯</b> <span>左下 部分床義歯 当院作成 2026年5月8日 経過期間 6か月</span></div>"
        "</div>"
    )
    inner = f'<div class="teeth"><div class="frame"></div>{side}</div>'
    return card("tooth-chart", "歯の状態", inner, 8)


def render():
    appt = (
        "14:30〜15:30（1時間）"
        "<small>15:30〜16:00 SPT</small>"
    )
    top = topbar(
        "歯科医師用",
        appt,
        [("change-patient", "患者様を変える"), ("change-role", "役割を変える")],
    )
    body = (
        '<main class="body doctor">'
        + _today()
        + _history()
        + intraoral(5, "c4")
        + _teeth()
        + spoken(
            4,
            ["右下6番 根管充填、側方加圧", "デンタルで確認、問題なし", "次回 支台築造と形成、2週間後ごろ"],
            "01:24",
        )
        + "</main>"
    )
    return page("doctor", "歯科医師の画面（見本）", top, bands_three(), body)
