"""G19l: 下書きの「やったこと」から「歯ごとの処置」の候補を拾い、人が選んだものを歯の状態と治療歴へ書く。

- 候補にするのは、(1) 歯が1本に決まる行（app/mockview/tooth_chart.py の site_teeth() で決まるもの。呼ぶだけで、決まり方はそちらの受け持ち）、
  (2) 処置の言葉が config/tooth_treatments.json の表にあるもの、の両方がそろった行だけ。どちらかが無ければ候補にしない（推し量らない）。
- Claude はここに出てこない（分けるのは memo.py で済んでいる。状態は表の言葉から決まり、人が選ぶ）。
- 書き込みは確定の取引の中（confirm.confirm）。古い状態は tooth_status_history に日付を付けて残す（治療計画の superseded_on と同じ考え）。
"""
import json
import re
from pathlib import Path

from app.ai.recpipe import RecError
from app.mockview import tooth_chart as tc

CONFIG = Path(__file__).resolve().parents[2] / "config" / "tooth_treatments.json"
TOOTH = re.compile(r"(?:右上|右下|左上|左下)\s*[1-8]\s*番")
REGION = re.compile(r"上顎|下顎|全顎|右側|左側")  # 歯のほかに部位の言葉があると、どの歯の話か1つに決まらない
FIELDS = ("crown", "root", "caries")


def load_table() -> list:
    try:
        rows = json.loads(CONFIG.read_text(encoding="utf-8"))["treatments"]
    except (OSError, ValueError, KeyError) as e:
        raise RecError(f"歯の処置の表（config/tooth_treatments.json）が読めません: {e}", 500)
    for r in rows:
        bad = [k for k in r["set"] if k not in FIELDS]
        if bad or not r["words"] or not r["label"]:
            raise RecError(f"歯の処置の表の書き方が正しくありません: {r.get('label')}", 500)
        if r["set"].get("crown") and r["set"]["crown"] not in tc.CROWNS:
            raise RecError(f"歯の処置の表の歯冠の言葉が正しくありません: {r['set']['crown']}", 500)
        if r["set"].get("root") and r["set"]["root"] not in tc.ROOTS_STATE:
            raise RecError(f"歯の処置の表の根の言葉が正しくありません: {r['set']['root']}", 500)
    return rows


def words_in(text: str, table: list) -> list:
    """行の中にある表の処置を、出てくる順に返す。長い言葉から先に当て、当たった所は別の言葉に使わない
    （「感染根管治療」の中の「根管」などを二重に拾わない）。"""
    pairs = sorted(((w, r) for r in table for w in r["words"]), key=lambda p: -len(p[0]))
    taken, hits = [False] * len(text), []
    for w, r in pairs:
        start = 0
        while True:
            i = text.find(w, start)
            if i < 0:
                break
            span = range(i, i + len(w))
            if not any(taken[j] for j in span):
                for j in span:
                    taken[j] = True
                hits.append((i, r))
            start = i + len(w)
    seen, out = set(), []
    for _i, r in sorted(hits, key=lambda h: h[0]):
        if r["label"] not in seen:
            seen.add(r["label"])
            out.append(r)
    return out


def one_tooth(text: str):
    """行の歯が1本に決まるときだけその歯番。複数の歯や、顎・側の言葉があるときは決まらない（None）。"""
    if len(TOOTH.findall(text)) != 1 or REGION.search(text):
        return None
    t = tc.site_teeth(text)
    return next(iter(t)) if len(t) == 1 else None


def state_of(raw) -> tuple:
    """表の1行（crown, root, caries, status）を (歯冠, 根, カリエス) にする。行が無い歯は健全・生活。"""
    if raw is None:
        return ("健全", "生活", False)
    return tc.parts(((raw["crown"], raw["root"], bool(raw["caries"])) if raw["crown"] else raw["status"]))


def after(before: tuple, effect: dict) -> tuple:
    crown, root, caries = before
    if "crown" in effect:
        crown = effect["crown"]
    if "root" in effect:
        root = effect["root"]
    if "caries" in effect:
        caries = bool(effect["caries"])
    return tc.parts((crown, root, caries))


def _teeth_rows(con, patient_id: int) -> dict:
    return {r["tooth"]: r for r in con.execute(
        "SELECT tooth, status, crown, root, caries FROM tooth_status WHERE patient_id = ?", (patient_id,))}


def candidates(con, patient_id: int, items: dict) -> list:
    """「やったこと」の行から候補を作る。1つの候補は {key, tooth, site, word, label, row, before, after}。
    key は「歯番:処置の名前」（確定のときに画面から戻ってくる。戻ってきたものがここに無ければ受け付けない）。"""
    table, rows, out, seen = load_table(), _teeth_rows(con, patient_id), [], set()
    for r in (items or {}).get("done", []):
        text = (r.get("text") or "").strip()
        tooth = one_tooth(text)
        if tooth is None:
            continue
        for t in words_in(text, table):
            key = f"{tooth}:{t['label']}"
            if key in seen:
                continue
            seen.add(key)
            b = state_of(rows.get(tooth))
            out.append({"key": key, "tooth": tooth, "site": site_name(tooth), "word": t["label"], "row": text,
                        "set": t["set"], "before": tc.describe(b), "after": tc.describe(after(b, t["set"]))})
    return out


def site_name(tooth: int) -> str:
    return {1: "右上", 2: "左上", 3: "左下", 4: "右下"}[tooth // 10] + f"{tooth % 10}番"


def apply(j, day: str, items: dict, picked: list):
    """人が選んだ候補だけを書く（確定の取引の中。失敗は RecError で、取引ごと戻る）。
    歯の状態: 古い状態は tooth_status_history に day の日付で残してから、表の言葉どおりに変える。
    治療歴: 日付＝診療回の日、部位＝歯、内容＝処置の名前。自院の印は、治療歴に1本の歯として入ることで付く（tooth_chart.own_teeth）。"""
    con, patient_id = j.con, j.patient_id
    if not picked:
        return []
    if not isinstance(picked, list) or any(not isinstance(k, str) for k in picked) or len(set(picked)) != len(picked):
        raise RecError("歯の処置の選び方が正しくありません")
    cands = {c["key"]: c for c in candidates(con, patient_id, items)}
    unknown = [k for k in picked if k not in cands]
    if unknown:
        raise RecError("歯の処置の候補に無いものが選ばれています: " + "、".join(unknown))
    chosen = [cands[k] for k in picked]
    seen = {}
    for c in chosen:  # 同じ歯の同じ所を2つの処置で変える選び方は、どちらが後か決められないので受け付けない
        for f in c["set"]:
            if (c["tooth"], f) in seen:
                raise RecError(f"{c['site']}に「{seen[(c['tooth'], f)]}」と「{c['word']}」の両方が選ばれています。どちらか1つにしてください")
            seen[(c["tooth"], f)] = c["word"]
    for c in chosen:
        row = con.execute("SELECT * FROM tooth_status WHERE patient_id = ? AND tooth = ?", (patient_id, c["tooth"])).fetchone()
        b = state_of(row)
        crown, root, caries = after(b, c["set"])
        status = tc.describe((crown, root, caries))
        if crown == "欠損":
            status = "欠損"
        if row:
            j.insert("tooth_status_history", patient_id=patient_id, tooth=c["tooth"], status=row["status"], crown=row["crown"],
                     root=row["root"], caries=row["caries"] or 0, superseded_on=day)
            j.update("tooth_status", row["id"], status=status, crown=crown, root=root, caries=int(caries))
        else:
            j.insert("tooth_status", patient_id=patient_id, tooth=c["tooth"], status=status, crown=crown, root=root, caries=int(caries))
        j.insert("treatment_history", patient_id=patient_id, done_date=day, site=c["site"], content=c["word"])
    return chosen
