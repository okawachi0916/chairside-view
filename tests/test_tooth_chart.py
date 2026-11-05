"""G23 / G07f: 歯の状態の絵。1本を「歯冠」と「根」の2つで描き、自院の治療は四角で囲む。"""
from app.mockview import tooth_chart as TC
from app.views import data as D
from tests.screen_helper import browser, check_screen, open_page, server  # noqa: F401

NAMES = {"見本 花子": 1, "見本 一郎": 2, "見本 太郎": 3, "見本 和子": 4, "見本 美咲": 5}


def _doctor_appt(pid):
    rows = [r for r in D.today_list() if r["patient_id"] == pid]
    return [r for r in rows if r["role"] == "doctor"][0]["id"] if any(r["role"] == "doctor" for r in rows) else rows[0]["id"]


def _chart(pg):
    return pg.evaluate("""() => {
        const svg = document.querySelector('[data-part="tooth-chart"] svg.tooth-svg');
        const teeth = {};
        for (const g of svg.querySelectorAll('g.tc-tooth:not(.pontic)')) {
          teeth[g.dataset.tooth] = {crown: g.dataset.crown, root: g.dataset.root,
            cap: !!g.querySelector('.tc-crown.cap'), crownDrawn: !!g.querySelector('.tc-crown'),
            fill: !!g.querySelector('.tc-fill'), caries: !!g.querySelector('.tc-caries'),
            dead: g.querySelectorAll('.tc-canal.dead').length, open: g.querySelectorAll('.tc-canal.open').length,
            filled: g.querySelectorAll('.tc-canal.filled').length, canals: g.querySelectorAll('.tc-canal').length};
        }
        const box = k => [...svg.querySelectorAll('.tc-box.' + k)].map(r => +r.dataset.tooth).sort((a, b) => a - b);
        const reds = [...svg.querySelectorAll('*')].filter(e => getComputedStyle(e).fill === 'rgb(198, 40, 40)').length;
        const noColors = new Set([...svg.querySelectorAll('.tc-no:not(.gone)')].map(t => getComputedStyle(t).fill));
        const lg = document.querySelector('[data-part="tooth-chart"] .tc-legend').getBoundingClientRect();
        const sv = svg.getBoundingClientRect();
        const legend = document.querySelector('[data-part="tooth-chart"] .tc-legend');
        return {teeth, done: box('done'), doing: box('doing'), reds, noColors: noColors.size,
                pontic: [...svg.querySelectorAll('g.tc-tooth.pontic')].map(g => +g.dataset.tooth),
                bridges: svg.querySelectorAll('.tc-bridge').length,
                pulp: svg.querySelectorAll('.tc-pulp, .tc-today').length,
                legendBelow: lg.top >= sv.bottom - 2, legendOneLine: lg.height < 26 && legend.scrollWidth <= legend.clientWidth,
                text: svg.textContent + legend.innerText};  // 横の義歯の記録（他院作成など）はデータなので見ない
    }""")


def test_parts_reads_old_and_new():
    assert TC.parts("RCT中") == ("健全", "根治中")
    assert TC.parts("根管治療済") == ("健全", "根充後")
    assert TC.parts("失活") == ("健全", "失活")
    assert TC.parts("残根") == ("残根", "失活")
    assert TC.parts(("残根", "生活")) == ("残根", "失活")  # 残根に生活歯はない
    assert TC.parts(("残根", "根充後")) == ("残根", "根充後")
    assert TC.parts("クラウン") == ("クラウン", "生活")
    assert TC.parts("C2") == ("C2", "生活") and TC.marks("C2")["caries"]
    assert TC.parts(("インレー+カリエス", "生活")) == ("インレー+カリエス", "生活")
    m = TC.marks("インレー+カリエス")
    assert m["fill"] and m["caries"] and not m["cap"]
    assert TC.parts("欠損") == ("欠損", "")
    assert TC.treated("CR") and TC.treated("RCT中") and not TC.treated("C2") and not TC.treated("残根")


def test_site_teeth_and_doing():
    assert TC.site_teeth("右下6番 根管充填") == {46}
    assert TC.site_teeth("下顎") == {t for q in (3, 4) for t in range(q * 10 + 1, q * 10 + 9)}
    assert TC.today_teeth(["右下6番 根管充填", "", "全顎"]) == {46}
    status = {46: "RCT中", 37: "CR", 15: "C2", 14: "欠損"}
    plans = ["右下6番 次回 支台築造", "左下7番 3か月様子を見る", "その間に 右上5番 の充填", "右上4番 ブリッジ", "上顎 SRP"]
    assert TC.doing_teeth(status, plans) == {46, 15}  # 様子を見る・欠損の歯・範囲の計画は入れない


def test_chart_draws_two_parts_boxes_and_no_red():
    svg = TC.chart_svg({46: ("クラウン", "根充後"), 25: ("インレー+カリエス", "生活"), 13: ("残根", "失活"),
                        11: ("健全", "生活"), 21: ("健全", "失活"), 22: ("健全", "根治中")},
                       own={46, 11}, today={11, 22}, doing={22})
    assert 'class="tc-pulp' not in svg and "tc-today" not in svg and "他院" not in svg
    g46 = svg.split('data-tooth="46" data-crown')[1].split("</g>")[0]
    assert "tc-crown cap" in g46 and "tc-canal filled" in g46  # 灰色の冠＋オレンジの根管
    g25 = svg.split('data-tooth="25" data-crown')[1].split("</g>")[0]
    assert "tc-fill" in g25 and "tc-caries" in g25
    g13 = svg.split('data-tooth="13" data-crown')[1].split("</g>")[0]
    assert "tc-crown" not in g13 and "tc-canal dead" in g13  # 残根は根だけ
    g11 = svg.split('data-tooth="11" data-crown')[1].split("</g>")[0]
    assert "tc-canal" not in g11  # 健全な生活歯は歯髄を描かない
    assert 'tc-box done" data-tooth="46"' in svg and 'tc-box doing" data-tooth="22"' in svg
    assert 'data-tooth="11" x=' not in svg  # 今日の処置の歯は囲まない


def test_five_patients(server, browser):  # noqa: F811
    charts = {}
    for name, pid in NAMES.items():
        pg = open_page(browser, server, f"/unit?appt={_doctor_appt(pid)}&role=doctor")
        pg.wait_for_selector('[data-part="tooth-chart"] svg.tooth-svg')
        pg.wait_for_timeout(300)
        c = charts[name] = _chart(pg)
        with D.con() as con:
            missing = {r[0] for r in con.execute(
                "SELECT tooth FROM tooth_status WHERE patient_id = ? AND COALESCE(crown, status) = '欠損'", (pid,))}
        assert not (set(map(int, c["teeth"])) & missing), f"{name}: 歯が無い所に描いている"
        assert c["reds"] == 0 and c["pulp"] == 0, f"{name}: 赤い歯髄か今日の処置の枠がある"
        assert "他院" not in c["text"] and "自院で治療済み" in c["text"], name
        assert c["noColors"] == 1, f"{name}: 歯の番号の色が分かれている"
        assert c["legendBelow"] and c["legendOneLine"], f"{name}: 凡例が絵の下の1行に収まらない"
        for t, v in c["teeth"].items():  # 色と形の決まり
            if v["root"] == "生活":
                assert v["canals"] == 0, (name, t)
            if v["root"] == "失活":
                assert v["dead"] and not v["open"] and not v["filled"], (name, t)
            if v["root"] == "根治中":
                assert v["open"] and not v["filled"], (name, t)
            if v["root"] == "根充後":
                assert v["filled"] and not v["open"], (name, t)
            assert v["crownDrawn"] == (v["crown"] != "残根"), (name, t)
        if pid == 1:
            check_screen(pg, ["tooth-chart"], ["自院で治療中", "根充後"], "G23.png")
        pg.close()

    hanako, taro, kazuko = charts["見本 花子"], charts["見本 太郎"], charts["見本 和子"]
    # 花子様: 右下6番は根治中（オレンジの枠の根管）で濃い四角
    assert hanako["teeth"]["46"]["root"] == "根治中" and hanako["teeth"]["46"]["open"]
    assert 46 in hanako["doing"]
    # 和子様: 左上5番はインレー＋カリエス（緑の充填と黒い点）。残根は根だけ
    k25 = kazuko["teeth"]["25"]
    assert k25["fill"] and k25["caries"]
    assert all(not kazuko["teeth"][str(t)]["crownDrawn"] for t in (13, 23, 33, 43) if str(t) in kazuko["teeth"])
    # 太郎様: ブリッジ3つ（支台6本、ポンティック6本）
    assert taro["bridges"] == 3 and sorted(taro["pontic"]) == [15, 16, 35, 36, 45, 46]
    # 「根充してクラウン」の歯が誰かに1本以上（灰色の冠＋オレンジの根管）
    assert any(v["cap"] and v["filled"] for c in charts.values() for v in c["teeth"].values())
    assert len({str(c["teeth"]) for c in charts.values()}) == 5


def test_outline_visible_on_light_and_dark(server, browser):  # noqa: F811
    """白抜きの歯の輪郭は、明るい地でも暗い地でも見える（地と歯の色の差を測る）。"""
    pg = open_page(browser, server, f"/unit?appt={_doctor_appt(1)}&role=doctor")
    pg.wait_for_selector('[data-part="tooth-chart"] svg.tooth-svg')

    def lum(rgb):
        vals = [int(x) / 255 for x in rgb[rgb.index("(") + 1:-1].split(",")[:3]]
        vals = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in vals]
        return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]

    def ratio(a, b):
        hi, lo = sorted([lum(a), lum(b)], reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    for bg in ("var(--c-canvas)", "var(--c-ink)"):
        pg.evaluate("bg => document.querySelector('[data-part=\"tooth-chart\"] .frame').style.background = bg", bg)
        frame, fill, stroke = pg.evaluate("""() => {
            const f = getComputedStyle(document.querySelector('[data-part="tooth-chart"] .frame')).backgroundColor;
            const c = getComputedStyle(document.querySelector('.tc-crown:not(.cap)'));
            return [f, c.fill, c.stroke]; }""")
        assert max(ratio(frame, fill), ratio(frame, stroke)) >= 4.5, (bg, frame, fill, stroke)
    pg.close()
