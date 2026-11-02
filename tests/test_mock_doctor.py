from tests.screen_helper import browser, check_screen, open_page, server  # noqa: F401

PARTS = [
    "today-appointment", "important", "medical-history", "today-treatment", "treatment-plan",
    "past-notes", "treatment-history", "intraoral-photos", "photo-list", "tooth-chart",
    "spoken-summary",
]
WORDS = [
    "歯科医師用", "見本 花子 様 58歳 女性 No. 0123 ユニット2", "2026年11月6日 金曜日",
    "14:30〜15:30（1時間）", "15:30〜16:00 SPT", "患者様を変える", "役割を変える",
    "重要事項", "ペニシリン系抗菌薬アレルギー", "ビスホスホネート製剤服用中",
    "全身既往・服薬", "高血圧（アムロジピン内服中）", "脂質異常症（ロスバスタチン内服中）",
    "骨粗鬆症（BP製剤内服中）", "申し送り", "長く口を開けているのがつらい方です",
    "今日の処置", "右下6番 根管充填", "根管治療 3回目", "治療計画",
    "右下6番 次回 支台築造と形成、そのあとクラウン", "左下7番 3か月様子を見る",
    "その間に 右上5番 の充填", "過去の診療メモ",
    "2026年10月23日 右下6番 根管貼薬、仮封、打診痛なし。症状がなければ次回根管充填",
    "2026年4月14日 右上5番 知覚過敏の処置", "治療歴", "口腔内写真", "スマホ",
    "歯の状態", "その他粘膜疾患 舌左縁 白板症",
    "義歯 左下 部分床義歯 当院作成 2026年5月8日 経過期間 6か月",
    "話した内容の整理", "右下6番 根管充填、側方加圧", "デンタルで確認、問題なし",
    "次回 支台築造と形成、2週間後ごろ", "録音中 01:24", "全画面",
]


def test_doctor_screen(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/mock/doctor")
    check_screen(pg, PARTS, WORDS, "G03.png")
    assert pg.locator("button:has-text('全画面')").count() == 6
    assert pg.locator("[data-part=photo-list] .ph").count() == 12
    assert pg.locator("[data-part=treatment-history] tbody tr").count() == 10
    # 全身既往・服薬は1行ずつで、4行が全部見える
    meds = pg.locator("[data-part=medical-history] ul.meds")
    assert meds.locator("li").count() == 4
    assert meds.evaluate("e => e.scrollHeight <= e.clientHeight + 1")
    # 重要事項は赤地に白文字
    assert pg.locator("[data-part=important]").evaluate(
        "e => getComputedStyle(e).backgroundColor") == "rgb(183, 28, 28)"
    assert pg.locator("[data-part=important] .lines").evaluate(
        "e => getComputedStyle(e).color") == "rgb(255, 255, 255)"
    # 名前は他の項目より大きい
    size = lambda sel: pg.locator(sel).first.evaluate("e => parseFloat(getComputedStyle(e).fontSize)")
    assert size(".pname") > size(".pinfo")
    pg.close()
