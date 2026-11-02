"""G23: 歯の状態の絵。花子様、太郎様、和子様で絵が変わり、歯が無い所は空く。"""
from app.mockview import tooth_chart as TC
from app.views import data as D
from tests.screen_helper import browser, check_screen, open_page, server  # noqa: F401

NAMES = {"見本 花子": 1, "見本 太郎": 3, "見本 和子": 4}


def _doctor_appt(pid):
    rows = [r for r in D.today_list() if r["patient_id"] == pid]
    return [r for r in rows if r["role"] == "doctor"][0]["id"] if any(r["role"] == "doctor" for r in rows) else rows[0]["id"]


def _chart(pg):
    return pg.evaluate("""() => {
        const svg = document.querySelector('[data-part="tooth-chart"] svg.tooth-svg');
        const drawn = [...svg.querySelectorAll('g.tc-tooth')].map(g => +g.dataset.tooth);
        const pontic = [...svg.querySelectorAll('g.tc-tooth.pontic')].map(g => +g.dataset.tooth);
        const caps = svg.querySelectorAll('g.tc-tooth:not(.pontic) .tc-crown.cap').length;
        const fills = svg.querySelectorAll('.tc-fill').length;
        const dead = svg.querySelectorAll('.tc-pulp.dead').length;
        const live = svg.querySelectorAll('.tc-pulp:not(.dead)').length;
        const bridges = svg.querySelectorAll('.tc-bridge').length;
        const today = [...svg.querySelectorAll('.tc-today')].map(r => +r.dataset.tooth);
        const own = [...svg.querySelectorAll('.tc-no.own')].map(t => +t.dataset.no);
        const other = [...svg.querySelectorAll('.tc-no.other')].map(t => +t.dataset.no);
        return {drawn, pontic, caps, fills, dead, live, bridges, today, own, other};
    }""")


def test_site_teeth():
    assert TC.site_teeth("右下6番 根管充填") == {46}
    assert TC.site_teeth("左上7番") == {27}
    assert TC.site_teeth("下顎") == {t for q in (3, 4) for t in range(q * 10 + 1, q * 10 + 9)}
    assert TC.site_teeth("上顎左側") == set(range(21, 29))
    assert TC.today_teeth(["右下6番 根管充填", "", "全顎"]) == {46}


def test_three_patients_differ_and_gaps_are_empty(server, browser):  # noqa: F811
    charts = {}
    for name, pid in NAMES.items():
        pg = open_page(browser, server, f"/unit?appt={_doctor_appt(pid)}&role=doctor")
        pg.wait_for_selector('[data-part="tooth-chart"] svg.tooth-svg')
        charts[name] = _chart(pg)
        with D.con() as c:
            missing = {r[0] for r in c.execute(
                "SELECT tooth FROM tooth_status WHERE patient_id = ? AND status = '欠損'", (pid,))}
        drawn = set(charts[name]["drawn"]) - set(charts[name]["pontic"])
        assert not (drawn & missing), f"{name}: 歯が無い所に描いている {drawn & missing}"
        if name == "見本 花子":
            check_screen(pg, ["tooth-chart"], ["自院", "他院"], "G23.png")
        pg.close()

    hanako, taro, kazuko = charts["見本 花子"], charts["見本 太郎"], charts["見本 和子"]
    # 花子様: 右下6番は根管治療中（失活の歯髄）で今日の処置の枠。CR 2本、クラウン1本、6本ない
    assert hanako["today"] == [46]
    assert hanako["dead"] >= 1 and hanako["fills"] == 2 and hanako["caps"] == 1
    assert len(hanako["drawn"]) == 26
    assert 46 in hanako["own"] and 26 in hanako["other"]
    # 太郎様: ブリッジ3つ（支台6本、ポンティック6本）。上の左の5番6番は空いたまま
    assert taro["bridges"] == 3 and sorted(taro["pontic"]) == [15, 16, 35, 36, 45, 46]
    assert 25 not in taro["drawn"] and 26 not in taro["drawn"]
    assert set(taro["other"]) >= {34, 37, 44, 47}
    # 和子様: 残根4本だけ。歯冠は描かず、歯髄は失活
    assert sorted(kazuko["drawn"]) == [13, 23, 33, 43]
    assert kazuko["dead"] == 4 and kazuko["live"] == 0
    assert kazuko["own"] == [] and kazuko["other"] == []  # 残根は処置した歯ではない
    assert len({str(c) for c in charts.values()}) == 3
