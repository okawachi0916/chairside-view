from tests.screen_helper import browser, check_screen, open_page, server  # noqa: F401

PARTS = ["today-appointment", "important", "next-appointment", "booked-appointment"]
WORDS = [
    "受付用", "見本 花子 様 58歳 女性 No. 0123 ユニット2", "2026年11月6日 金曜日",
    "14:30〜15:30 RCT", "15:30〜16:00 SPT", "患者様を変える", "重要事項",
    "ペニシリン系抗菌薬アレルギー", "ビスホスホネート製剤服用中", "受付メモ",
    "お子さん3人と同じ時間で予約を取る", "予約日時", "今回", "2026年11月6日 金曜日", "時間", "14:30〜16:00（1時間30分）", "最近の来院", "来院しやすい曜日・時間帯", "過去1年の来院13回",
    "金曜の午後", "月", "火", "水", "木", "金", "土", "午前", "午後", "夕方", "キャンセル傾向", "1回",
    "予約14回のうち 無断キャンセル 0回", "2026/3/12(木) 当日の朝に電話あり",
    "処置と次回の予約", "今日", "右下第一大臼歯 RCT、SPT＋TBI", "次回", "支台築造＋形成印象",
    "歯科医師 大川内", "60分枠", "2週間後ごろ", "予約済み", "2027年2月5日 歯科衛生士 田中 3か月SPT",
    "過去の物品購入", "買った日", "品名", "数", "過去の処方", "処方日", "薬", "量",
    "ロキソプロフェン錠 60mg", "クラリスロマイシン錠 200mg", "診察券 裏面",
    "次回のご予約 11月6日(金) 14:30", "全画面",
]


def test_reception_screen(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/mock/reception")
    check_screen(pg, PARTS, WORDS, "G05.png")
    assert pg.locator("button:has-text('全画面')").count() == 2
    # 受付は声を使わない。マイク、スマホ、口腔内写真は置かない
    for part in ("intraoral-photos", "photo-list", "spoken-summary"):
        assert pg.locator(f'[data-part="{part}"]').count() == 0
    assert pg.locator("button:has-text('スマホ')").count() == 0
    assert pg.locator("svg.mic").count() == 0
    assert pg.locator("button:has-text('役割を変える')").count() == 0
    assert pg.locator("[data-part=booked-appointment]").count() == 1
    assert pg.locator(".hc-day:has-text('金')").count() == 1
    assert pg.locator(".hc-cell").count() == 18
    assert pg.locator(".hc-cell.top").inner_text() == "6"
    pg.close()
