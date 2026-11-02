from tests.screen_helper import browser, check_screen, open_page, server  # noqa: F401

PARTS = [
    "today-appointment", "important", "medical-history", "intraoral-photos", "photo-list",
    "spoken-summary", "perio-exam",
]
WORDS = [
    "歯科衛生士用", "見本 花子 様 58歳 女性 No. 0123 ユニット2", "2026年11月6日 金曜日",
    "15:30〜16:00（30分）", "前の予約 14:30〜15:30 RCT", "患者様を変える", "役割を変える",
    "重要事項", "ペニシリン系抗菌薬アレルギー", "ビスホスホネート製剤服用中",
    "全身既往・服薬", "高血圧（アムロジピン内服中）", "脂質異常症（ロスバスタチン内服中）",
    "骨粗鬆症（BP製剤内服中）", "申し送り", "長く口を開けているのがつらい方です",
    "口腔内写真", "スマホで写真をやり取り", "話した内容の整理", "右下奥の清掃を指導", "寝る前の歯間ブラシを継続",
    "録音中 00:48", "メンテナンス間隔", "3か月ごと", "前回 2026年8月7日", "使用ケア用品・購入履歴",
    "歯間ブラシ SS", "2026/9/18", "フッ素ジェル", "2026/8/7", "歯ブラシ やわらかめ",
    "洗口液", "2026/5/8", "デンタルフロス", "2026/2/6", "歯周基本検査", "検査日 2026年8月7日",
    "4mm以上", "6本", "前回 9本", "BOP", "15%", "前回 19%", "PCR", "18%", "前回 24%",
    "動揺のある歯", "0本", "前回 0本", "検査した歯", "26本", "上顎", "下顎", "動揺度", "プラークチャート", "ポケット", "歯番", "入力", "全画面",
]


def test_hygienist_screen(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/mock/hygienist")
    check_screen(pg, PARTS, WORDS, "G04.png")
    assert pg.locator("button:has-text('全画面')").count() == 5
    assert pg.locator("[data-part=photo-list] .ph").count() >= 6
    t = pg.locator("[data-part=perio-exam] table.perio")
    assert t.locator("tr").count() == 7
    assert t.locator("td.deep").count() == 6
    assert t.locator("td.bop").count() >= 1
    # 「入力」ボタンは全画面の横に並ぶ。今は押しても表示は変わらない
    card = pg.locator("[data-part=perio-exam]")
    inp, full = card.locator("button.input"), card.locator("button.full")
    assert inp.count() == 1 and inp.inner_text() == "入力"
    ib, fb = inp.bounding_box(), full.bounding_box()
    assert abs(ib["y"] - fb["y"]) < 3 and ib["x"] < fb["x"]
    before = card.inner_html()
    inp.click()
    assert card.inner_html() == before
    # BOP は赤の太字
    assert t.locator("td.bop").first.evaluate(
        "e => [getComputedStyle(e).color, getComputedStyle(e).fontWeight].join()") == "rgb(208, 0, 0),900"
    # 歯番は上顎と下顎で共通の1行。8〜1、1〜8
    nums = t.locator("tr.no td").all_inner_texts()
    assert nums == ["8", "7", "6", "5", "4", "3", "2", "1", "1", "2", "3", "4", "5", "6", "7", "8"]
    # プラークチャートはマス目いっぱい
    ok = t.locator("td.pl").first.evaluate(
        "e => { const a = e.getBoundingClientRect(), b = e.querySelector('svg').getBoundingClientRect();"
        " return Math.abs(a.width - b.width) < 3 && Math.abs(a.height - b.height) < 3; }")
    assert ok
    pg.close()
