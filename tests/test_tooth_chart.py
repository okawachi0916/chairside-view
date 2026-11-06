"""G23 / G07f / G07g: 歯の状態の絵。1本を「歯冠」「根」「カリエスの印」で描き、自院の治療は四角で囲む。
G07g: 凡例は絵の左に縦、絵は大きく、インプラント・ブリッジ・カリエスの重ね、有床義歯の あり／なし と作成元。"""
from pathlib import Path

from app.mockview import tooth_chart as TC
from app.views import data as D
from tests.screen_helper import browser, check_screen, open_page, server  # noqa: F401

NAMES = {"見本 花子": 1, "見本 一郎": 2, "見本 太郎": 3, "見本 和子": 4, "見本 美咲": 5}
OLD_WORD = "根充" + "後"  # G07f のときの名前。画面にもコードにも出さない（DB を直す update.py だけが読む）
BEFORE_TOOTH_W = 44.9  # G07f の画面での1本の幅（px、1920×1080 で測った値）


def _doctor_appt(pid):
    rows = [r for r in D.today_list() if r["patient_id"] == pid]
    return [r for r in rows if r["role"] == "doctor"][0]["id"] if any(r["role"] == "doctor" for r in rows) else rows[0]["id"]


def _chart(pg):
    return pg.evaluate("""() => {
        const card = document.querySelector('[data-part="tooth-chart"]');
        const svg = card.querySelector('svg.tooth-svg');
        const teeth = {};
        for (const g of svg.querySelectorAll('g.tc-tooth:not(.pontic)')) {
          teeth[g.dataset.tooth] = {crown: g.dataset.crown, root: g.dataset.root, caries: g.dataset.caries === '1',
            title: g.querySelector('title').textContent,
            cap: !!g.querySelector('.tc-crown.cap'), crownDrawn: !!g.querySelector('.tc-crown'),
            fill: !!g.querySelector('.tc-fill'), dot: !!g.querySelector('.tc-caries'),
            fixture: g.querySelectorAll('.tc-fixture').length, threads: g.querySelectorAll('.tc-thread').length,
            roots: g.querySelectorAll('.tc-root').length,
            dead: g.querySelectorAll('.tc-canal.dead').length, open: g.querySelectorAll('.tc-canal.open').length,
            filled: g.querySelectorAll('.tc-canal.filled').length, canals: g.querySelectorAll('.tc-canal').length};
        }
        const pontics = [...svg.querySelectorAll('g.tc-tooth.pontic')].map(g => ({tooth: +g.dataset.tooth,
            cap: !!g.querySelector('.tc-crown.cap'), roots: g.querySelectorAll('.tc-root').length}));
        const box = k => [...svg.querySelectorAll('.tc-box.' + k)].map(r => +r.dataset.tooth).sort((a, b) => a - b);
        const reds = [...svg.querySelectorAll('*')].filter(e => getComputedStyle(e).fill === 'rgb(198, 40, 40)').length;
        const noColors = new Set([...svg.querySelectorAll('.tc-no:not(.gone)')].map(t => getComputedStyle(t).fill));
        const r = e => { const b = e.getBoundingClientRect(); return {l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height}; };
        // 絵が実際に描かれている範囲（viewBox を枠に合わせて縮めた大きさ、右寄せ）
        const s = r(svg), vb = svg.viewBox.baseVal, k = Math.min(s.w / vb.width, s.h / vb.height);
        const drawn = {l: s.r - vb.width * k, r: s.r, t: s.t + (s.h - vb.height * k) / 2, b: s.t + (s.h + vb.height * k) / 2};
        const legend = card.querySelector('.tc-legend'), notes = card.querySelector('.tc-notes'), frame = card.querySelector('.frame');
        const rows = [...legend.children].map(e => r(e));
        const done = card.querySelector('.tc-box.done');
        return {teeth, pontics, done: box('done'), doing: box('doing'), reds, noColors: noColors.size,
                bridges: svg.querySelectorAll('.tc-bridge').length,
                pulp: svg.querySelectorAll('.tc-pulp, .tc-today').length,
                toothW: 56 * k, drawn, legend: r(legend), legendRows: rows.length,
                legendTops: rows.map(x => Math.round(x.t)), notes: r(notes), frame: r(frame),
                notesFit: notes.scrollHeight <= notes.clientHeight + 1 && r(notes).b <= r(frame).b + 1,
                legendSizes: [...new Set([...legend.querySelectorAll('span')].map(e => getComputedStyle(e).fontSize + '/' + getComputedStyle(e).fontWeight))],
                doneDash: done ? getComputedStyle(done).strokeDasharray : null,
                has: notes.querySelector('.tc-has') ? notes.querySelector('.tc-has').textContent : '',
                hasBg: notes.querySelector('.tc-has') ? getComputedStyle(notes.querySelector('.tc-has')).backgroundColor : '',
                tags: [...notes.querySelectorAll('.tc-tag')].map(e => [e.textContent, getComputedStyle(e).backgroundColor, getComputedStyle(e).color]),
                notesText: notes.innerText, legendText: legend.innerText, body: document.body.innerText,
                scroll: document.documentElement.scrollHeight > innerHeight || document.documentElement.scrollWidth > innerWidth,
                text: svg.textContent + legend.innerText};
    }""")


def test_parts_reads_old_and_new():
    assert TC.parts("RCT中") == ("健全", "根治中", False)
    assert TC.parts("根管治療済") == ("健全", "根充済", False)
    assert TC.parts("失活") == ("健全", "失活", False)
    assert TC.parts("残根") == ("残根", "失活", False)
    assert TC.parts(("残根", "生活")) == ("残根", "失活", False)  # 残根に生活歯はない
    assert TC.parts(("残根", "根充済")) == ("残根", "根充済", False)
    assert TC.parts("クラウン") == ("クラウン", "生活", False)
    # カリエスは別の印。今までの「C2」「インレー+カリエス」も読み替える
    assert TC.parts("C2") == ("健全", "生活", True)
    assert TC.parts(("インレー+カリエス", "生活")) == ("インレー", "生活", True)
    assert TC.parts(("クラウン", "根充済", 1)) == ("クラウン", "根充済", True)
    assert TC.parts(("ブリッジ支台", "生活", True)) == ("ブリッジ支台", "生活", True)
    # インプラント: 上部構造があれば冠、無ければ「なし」
    assert TC.parts(("クラウン", "インプラント")) == ("クラウン", "インプラント", False)
    assert TC.parts(("なし", "インプラント")) == ("なし", "インプラント", False)
    assert TC.parts("欠損") == ("欠損", "", False)
    assert TC.treated("CR") and TC.treated("RCT中") and TC.treated(("なし", "インプラント"))
    assert not TC.treated("C2") and not TC.treated("残根")


def test_describe_in_words():
    assert TC.describe(("インレー", "生活", 1)) == "インレー＋カリエス"
    assert TC.describe(("クラウン", "根充済", 1)) == "クラウン＋カリエス、根充済"
    assert TC.describe(("健全", "生活", 1)) == "カリエス"
    assert TC.describe(("健全", "生活")) == "健全"
    assert TC.describe(("クラウン", "インプラント")) == "インプラント（上部構造あり）"
    assert TC.describe(("なし", "インプラント")) == "インプラント（上部構造なし）"
    assert TC.describe("", pontic=True) == "ブリッジのポンティック"
    assert TC.describe(("残根", "失活")) == "残根、失活"


def test_site_teeth_and_doing():
    assert TC.site_teeth("右下6番 根管充填") == {46}
    assert TC.site_teeth("下顎") == {t for q in (3, 4) for t in range(q * 10 + 1, q * 10 + 9)}
    assert TC.today_teeth(["右下6番 根管充填", "", "全顎"]) == {46}
    status = {46: "RCT中", 37: "CR", 15: "C2", 14: "欠損"}
    plans = ["右下6番 次回 支台築造", "左下7番 3か月様子を見る", "その間に 右上5番 の充填", "右上4番 ブリッジ", "上顎 SRP"]
    assert TC.doing_teeth(status, plans) == {46, 15}  # 様子を見る・欠損の歯・範囲の計画は入れない


def _g(svg, t):
    return svg.split(f'data-tooth="{t}" data-crown')[1].split("</g>")[0]


def test_chart_draws_parts_implant_bridge_and_boxes():
    svg = TC.chart_svg({46: ("クラウン", "根充済", 1), 25: ("インレー", "生活", 1), 13: ("残根", "失活"),
                        11: ("健全", "生活"), 21: ("健全", "失活"), 22: ("健全", "根治中"),
                        36: ("クラウン", "インプラント"), 37: ("なし", "インプラント"),
                        14: ("ブリッジ支台", "生活", 1), 15: "欠損", 16: ("ブリッジ支台", "根充済")},
                       own={46, 11}, today={11, 22}, doing={22})
    assert 'class="tc-pulp' not in svg and "tc-today" not in svg and "他院" not in svg and OLD_WORD not in svg
    g46 = _g(svg, 46)
    assert "tc-crown cap" in g46 and "tc-canal filled" in g46 and "tc-caries" in g46  # 灰色の冠＋オレンジの根管＋黒い点
    g25 = _g(svg, 25)
    assert "tc-fill" in g25 and "tc-caries" in g25
    assert "tc-crown" not in _g(svg, 13) and "tc-canal dead" in _g(svg, 13)  # 残根は根だけ
    assert "tc-canal" not in _g(svg, 11)  # 健全な生活歯は歯髄を描かない
    g36, g37 = _g(svg, 36), _g(svg, 37)
    assert "tc-fixture" in g36 and "tc-thread" in g36 and "tc-crown cap" in g36 and "tc-root" not in g36
    assert "tc-fixture" in g37 and "tc-thread" in g37 and "tc-crown" not in g37  # 上部構造なしは冠を描かない
    assert "tc-crown cap" in _g(svg, 14) and "tc-caries" in _g(svg, 14)  # 支台にもカリエスを重ねられる
    pontic = svg.split('class="tc-tooth pontic" data-tooth="15">')[1].split("</g>")[0]
    assert "tc-crown cap" in pontic and "tc-root" not in pontic and "ポンティック" in pontic
    assert svg.count("tc-bridge") == 1
    assert 'tc-box done" data-tooth="46"' in svg and 'tc-box doing" data-tooth="22"' in svg
    assert 'data-tooth="11" x=' not in svg  # 今日の処置の歯は囲まない


def test_appliance_text():
    own = TC.appliance_html([{"site": "上顎", "kind": "総義歯", "made_by": "当院作成", "date": "2024年3月15日"},
                             {"site": "下顎", "kind": "総義歯", "made_by": "当院作成", "date": "2024年3月15日"}])
    assert "tc-has yes" in own and "あり" in own and "自院作成" in own and "当院" not in own
    assert "上顎・下顎 総義歯" in own and own.count("tc-dent-row") == 1  # 同じ物は1行にまとめる
    other = TC.appliance_html([{"site": "下顎", "kind": "ブリッジ", "made_by": "他院作成", "date": ""}])
    assert "tc-has no" in other and "なし" in other and "tc-tag other" in other and "他院作成" in other
    assert "tc-has no" in TC.appliance_html([])


def test_no_old_word_in_code():
    """「根充後」の字は、古いデータベースを直す update.py のほかには無い。"""
    root = Path(__file__).resolve().parents[1]
    hits = []
    for d in ("app", "config", "scripts", "docs"):
        for p in (root / d).rglob("*"):
            if p.suffix in (".py", ".js", ".json", ".html", ".css", ".md", ".txt") and p.name != "update.py":
                if OLD_WORD in p.read_text(encoding="utf-8", errors="ignore"):
                    hits.append(str(p.relative_to(root)))
    assert not hits, hits


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
        assert "他院" not in c["text"] and "自院で治療済み" in c["text"] and "インプラント" in c["legendText"], name
        assert OLD_WORD not in c["body"], name
        assert c["noColors"] == 1, f"{name}: 歯の番号の色が分かれている"
        assert not c["scroll"], f"{name}: 画面にスクロールが出る"
        # 凡例は絵の左に縦に並ぶ。字の大きさと太さは1つ
        assert c["legend"]["r"] <= c["drawn"]["l"] and c["legendRows"] >= 5, name
        assert c["legendTops"] == sorted(c["legendTops"]) and len(set(c["legendTops"])) == c["legendRows"], name
        assert len(c["legendSizes"]) == 1, (name, c["legendSizes"])
        # 絵は G07f より大きい
        assert c["toothW"] > BEFORE_TOOTH_W, (name, c["toothW"])  # 試験の画面（高さ1030）でも前の1080より大きい
        # 有床義歯の表示は絵に重ならず、枠の中に全部見える
        assert c["notes"]["r"] <= c["drawn"]["l"] and c["notesFit"], name
        assert c["has"] in ("あり", "なし"), name
        for t, v in c["teeth"].items():  # 色と形の決まり
            if v["root"] == "生活":
                assert v["canals"] == 0, (name, t)
            if v["root"] == "失活":
                assert v["dead"] and not v["open"] and not v["filled"], (name, t)
            if v["root"] == "根治中":
                assert v["open"] and not v["filled"], (name, t)
            if v["root"] == "根充済":
                assert v["filled"] and not v["open"], (name, t)
            if v["root"] == "インプラント":
                assert v["fixture"] and v["threads"] and not v["roots"], (name, t)
                assert v["cap"] == (v["crown"] == "クラウン") and v["crownDrawn"] == v["cap"], (name, t)
            else:
                assert v["crownDrawn"] == (v["crown"] != "残根"), (name, t)
            assert v["dot"] == v["caries"], (name, t)
        for p in c["pontics"]:
            assert p["cap"] and not p["roots"], (name, p)
        if pid == 1:
            check_screen(pg, ["tooth-chart"], ["自院で治療中", "根充済", "有床義歯", "自院作成"], "G23.png")
        pg.close()

    hanako = charts["見本 花子"]
    t = hanako["teeth"]
    kinds = {
        "健全": any(v["crown"] == "健全" and v["root"] == "生活" and not v["caries"] for v in t.values()),
        "充填": any(v["fill"] and not v["caries"] for v in t.values()),
        "クラウン": any(v["crown"] == "クラウン" and v["root"] == "生活" for v in t.values()),
        "ブリッジ": hanako["bridges"] >= 1 and len(hanako["pontics"]) >= 1
                    and any(v["crown"] == "ブリッジ支台" for v in t.values()),
        "カリエスだけ": any(v["crown"] == "健全" and v["caries"] for v in t.values()),
        "充填＋カリエス": any(v["fill"] and v["dot"] for v in t.values()),
        "失活": any(v["root"] == "失活" and v["crown"] != "残根" for v in t.values()),
        "根治中": any(v["root"] == "根治中" for v in t.values()),
        "根充済": any(v["root"] == "根充済" and not v["cap"] for v in t.values()),
        "根充済＋クラウン": any(v["root"] == "根充済" and v["crown"] == "クラウン" for v in t.values()),
        "残根": any(v["crown"] == "残根" for v in t.values()),
        "欠損": bool(set(range(11, 49)) - set(map(int, t)) - {p["tooth"] for p in hanako["pontics"]}),
        "自院で治療済みの枠": bool(hanako["done"]),
        "自院で治療中の枠": bool(hanako["doing"]),
        "有床義歯の表示": hanako["has"] == "あり" and "自院作成" in hanako["notesText"],
    }
    assert all(kinds.values()), [k for k, v in kinds.items() if not v]
    # 花子様: 右下6番は根治中（台本1）で濃い四角。治療済みの枠は点線
    assert t["46"]["root"] == "根治中" and t["46"]["open"] and 46 in hanako["doing"]
    assert hanako["doneDash"] not in (None, "none")
    # 花子様にインプラントは入れない（AI の見本の質問「インプラントの記録は？」は「記録がありません」。院長の決定 11/5）
    assert not any(v["root"] == "インプラント" for v in t.values())
    # 文字の説明（絵の中の title）でもカリエスの重ね・ポンティックが分かる
    titles = " ".join(v["title"] for v in t.values())
    assert "CR＋カリエス" in titles and "カリエス" in titles

    # ほかの患者様にも、インプラント・ブリッジ・充填＋カリエスがそれぞれ1本以上
    others = [c for n, c in charts.items() if n != "見本 花子"]
    # インプラントは上部構造あり・なしの両方
    imp = [v for c in others for v in c["teeth"].values() if v["root"] == "インプラント"]
    assert any(v["cap"] for v in imp) and any(not v["crownDrawn"] for v in imp)
    assert {"インプラント（上部構造あり）", "インプラント（上部構造なし）"} <= {v["title"].split(" ", 1)[1] for v in imp}
    assert any(c["bridges"] for c in others)
    assert any(v["fill"] and v["dot"] for c in others for v in c["teeth"].values())
    # 和子様: 左上5番はインレー＋カリエス（緑の充填と黒い点）。残根は根だけ
    kazuko, taro = charts["見本 和子"], charts["見本 太郎"]
    assert kazuko["teeth"]["25"]["fill"] and kazuko["teeth"]["25"]["dot"]
    assert all(not kazuko["teeth"][str(x)]["crownDrawn"] for x in (13, 23, 33, 43))
    # 太郎様: ブリッジ3つ（支台6本、ポンティック6本）
    assert taro["bridges"] == 3 and sorted(p["tooth"] for p in taro["pontics"]) == [15, 16, 35, 36, 45, 46]
    # 有床義歯: あり（墨の札）と なし（色の無い札）、自院作成（青）と他院作成（琥珀）が見分けられる
    assert hanako["has"] == "あり" and charts["見本 一郎"]["has"] == "なし"
    assert hanako["hasBg"] != charts["見本 一郎"]["hasBg"]
    own_tag = [x for x in kazuko["tags"] if x[0] == "自院作成"][0]
    other_tag = [x for x in taro["tags"] if x[0] == "他院作成"][0]
    assert own_tag[1:] != other_tag[1:]
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
    # 自院で治療済みの点線の枠は、灰色の地の上でも見える
    pg.evaluate("() => document.querySelector('[data-part=\"tooth-chart\"] .frame').style.background = ''")
    frame, box = pg.evaluate("""() => [getComputedStyle(document.querySelector('[data-part="tooth-chart"] .frame')).backgroundColor,
        getComputedStyle(document.querySelector('.tc-box.done')).stroke]""")
    assert ratio(frame, box) >= 4.5, (frame, box)
    pg.close()
