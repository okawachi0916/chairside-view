"""データベースの表の定義。作る処理も、足りない表と列を足す処理もここにある。

列は (名前, 型, 初期値, 必須) の4つ。初期値が None なら空 (NULL)。
あとから列を足すときは、必須と外部キーは付けられないので、型と初期値だけで足す。
"""
import sqlite3

# 診療回に結びつく表は (visit_id, patient_id) の組で診療回を指す。
# こうすると、別の患者様の診療回につなげられない。
_VISIT_FK = "FOREIGN KEY (visit_id, patient_id) REFERENCES visits(id, patient_id)"
_PATIENT_FK = "FOREIGN KEY (patient_id) REFERENCES patients(id)"

TABLES = {
    "patients": {
        "cols": [
            ("chart_no", "TEXT", None, True),
            ("name", "TEXT", None, True),
            ("name_kana", "TEXT", "''", True),
            ("birth_date", "TEXT", None, True),
            ("sex", "TEXT", "''", True),
        ],
        "extra": ["UNIQUE (chart_no)"],
    },
    "appointments": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("appt_date", "TEXT", None, True),
            ("start_time", "TEXT", None, True),
            ("end_time", "TEXT", None, True),
            ("role", "TEXT", "'doctor'", True),
            ("unit", "INTEGER", None, False),
            ("treatment", "TEXT", "''", True),
            ("detail", "TEXT", "''", True),
            ("detail_sub", "TEXT", "''", True),
            ("reception_text", "TEXT", "''", True),
            ("staff_name", "TEXT", "''", True),
            ("status", "TEXT", "'booked'", True),
        ],
        "extra": [_PATIENT_FK],
    },
    "visits": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("appointment_id", "INTEGER", None, False),
            ("visit_date", "TEXT", None, True),
            ("start_time", "TEXT", "''", True),
            ("role", "TEXT", "'doctor'", True),
            ("unit", "INTEGER", None, False),
            ("status", "TEXT", "'done'", True),
        ],
        "extra": [_PATIENT_FK, "UNIQUE (id, patient_id)"],
    },
    "important_notes": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("seq", "INTEGER", "0", True),
            ("body", "TEXT", None, True),
            ("period", "TEXT", "''", True),  # 起きた時期
            ("detail", "TEXT", "''", True),  # 起きたこと
        ],
        "extra": [_PATIENT_FK],
    },
    "medical_histories": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("seq", "INTEGER", "0", True),
            ("condition", "TEXT", None, True),
            ("medication", "TEXT", "''", True),
            ("since", "TEXT", "''", True),   # いつから (全画面の表)
            ("clinic", "TEXT", "''", True),  # 通院先
        ],
        "extra": [_PATIENT_FK],
    },
    "handovers": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("body", "TEXT", None, True),
        ],
        "extra": [_PATIENT_FK],
    },
    "reception_memos": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("body", "TEXT", None, True),
            ("written_on", "TEXT", "''", True),  # 書いた時期
        ],
        "extra": [_PATIENT_FK],
    },
    "treatment_plans": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("seq", "INTEGER", "0", True),
            ("kind", "TEXT", "'plan'", True),  # plan=治療計画の1行 / next=次回の予定 / policy=治療方針
            ("body", "TEXT", None, True),
            ("staff_role", "TEXT", "''", True),
            ("staff_name", "TEXT", "''", True),
            ("minutes", "INTEGER", None, False),
            ("timing", "TEXT", "''", True),
            ("superseded_on", "TEXT", None, False),  # 変更・削除された古い計画。日付を付けて残す（空なら今の計画）
        ],
        "extra": [_PATIENT_FK],
    },
    "clinical_notes": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("visit_id", "INTEGER", None, True),
            ("note_date", "TEXT", None, True),
            ("author_role", "TEXT", "'doctor'", True),
            ("body", "TEXT", None, True),
        ],
        "extra": [_PATIENT_FK, _VISIT_FK],
    },
    "treatment_history": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("done_date", "TEXT", None, True),
            ("site", "TEXT", "''", True),
            ("content", "TEXT", None, True),
        ],
        "extra": [_PATIENT_FK],
    },
    "photos": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("number", "INTEGER", None, True),  # 患者様の中の通し番号
            ("taken_on", "TEXT", None, True),
            ("kind", "TEXT", "'intraoral'", True),
            ("file", "TEXT", "''", True),  # data/runtime/photos の中の名前。空なら画像なし
        ],
        "extra": [_PATIENT_FK, "UNIQUE (patient_id, number)"],
    },
    "tooth_status": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("tooth", "INTEGER", None, True),  # FDI の歯番 (11〜48)
            ("status", "TEXT", None, True),  # 今までの1つの状態の文字（欠損の見分けにも使う）
            # G07f: 歯冠（健全/CR/インレー/充填/クラウン/ブリッジ支台/残根/欠損/なし）と
            # 根（生活/失活/根治中/根充済/インプラント）。空なら status を読み替える（app/mockview/tooth_chart.py の parts）
            ("crown", "TEXT", None, False),
            ("root", "TEXT", None, False),
            ("caries", "INTEGER", "0", False),  # G07g: カリエスは歯冠とは別の印（1=あり）
        ],
        "extra": [_PATIENT_FK, "UNIQUE (patient_id, tooth)"],
    },
    "mucosal_conditions": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("site", "TEXT", None, True),
            ("name", "TEXT", None, True),
        ],
        "extra": [_PATIENT_FK],
    },
    "dentures": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("site", "TEXT", None, True),
            ("kind", "TEXT", None, True),
            ("made_by", "TEXT", "''", True),
            ("made_on", "TEXT", None, False),
        ],
        "extra": [_PATIENT_FK],
    },
    "perio_exams": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("exam_date", "TEXT", None, True),
            ("kind", "TEXT", "'basic'", True),
        ],
        "extra": [_PATIENT_FK, "UNIQUE (patient_id, exam_date)"],
    },
    "perio_teeth": {
        "cols": [
            ("exam_id", "INTEGER", None, True),
            ("tooth", "INTEGER", None, True),
            ("pocket", "INTEGER", None, True),  # 基本検査は1本に1つ (mm)
            ("bop", "INTEGER", "0", True),
            ("plaque", "TEXT", "'0000'", True),  # 近心・遠心・頬側・舌側の順、1が付着
            ("mobility", "INTEGER", "0", True),
        ],
        "extra": ["FOREIGN KEY (exam_id) REFERENCES perio_exams(id)", "UNIQUE (exam_id, tooth)"],
    },
    "maintenance_intervals": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("months", "INTEGER", None, True),
            ("last_date", "TEXT", None, False),
        ],
        "extra": [_PATIENT_FK, "UNIQUE (patient_id)"],
    },
    "care_purchases": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("item", "TEXT", None, True),
            ("last_date", "TEXT", None, True),
        ],
        "extra": [_PATIENT_FK, "UNIQUE (patient_id, item)"],
    },
    "goods_purchases": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("bought_on", "TEXT", None, True),
            ("item", "TEXT", None, True),
            ("qty", "INTEGER", "1", True),
        ],
        "extra": [_PATIENT_FK],
    },
    "prescriptions": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("prescribed_on", "TEXT", None, True),
            ("drug", "TEXT", None, True),
            ("amount", "TEXT", "''", True),
        ],
        "extra": [_PATIENT_FK],
    },
    "cancellations": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("appointment_id", "INTEGER", None, False),
            ("cancel_date", "TEXT", None, True),
            ("no_show", "INTEGER", "0", True),
            ("reason", "TEXT", "''", True),
        ],
        "extra": [_PATIENT_FK],
    },
    # 確定前の下書き。確定するまで診療メモには入れない。
    "drafts": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("visit_id", "INTEGER", None, True),
            ("kind", "TEXT", "'spoken_summary'", True),
            ("body", "TEXT", "''", True),  # 要約。1行に1項目
            ("transcript", "TEXT", "''", True),  # 話したままの文字
            ("status", "TEXT", "'draft'", True),  # draft=確定前 / confirmed=確定済み
            ("created_at", "TEXT", "''", True),
            ("confirmed_at", "TEXT", None, False),
            ("recording_id", "INTEGER", None, False),  # もとの録音。1つの録音から下書きは1つだけ
            ("items", "TEXT", "'{}'", True),  # 5つの項目と抜き出し (JSON)
            ("fixed_transcript", "TEXT", "''", True),  # 聞き違いを直した文字。5つに分けるのはこちら（空なら直していない）
            ("fixes", "TEXT", "'[]'", True),  # 直した聞き違い [{"from","to","by"}]。画面で「元→直し」を見せる
            ("combined", "INTEGER", "0", True),  # 1=診療回の区切りを全部まとめた要約（recording_id は最後の区切り）
            ("doubts", "TEXT", "'[]'", True),  # 清書で「迷う」と印を付けた言葉（画面で印を付ける）
            ("polish_note", "TEXT", "''", True),  # 清書を使わなかった理由（空なら清書を使った）
        ],
        "extra": [_PATIENT_FK, _VISIT_FK],
    },
    # 録音（診療回の「区切り」）。患者様なしの録音は patient_id / visit_id が空。状態は日本語の10個。
    "recordings": {
        "cols": [
            ("rec_no", "INTEGER", "0", True),  # 録音の番号 (開いた順)
            ("started_at", "TEXT", "''", True),
            ("duration_sec", "REAL", "0", True),
            ("patient_id", "INTEGER", None, False),
            ("visit_id", "INTEGER", None, False),
            ("audio_file", "TEXT", "''", True),
            ("state", "TEXT", "'録音中'", True),
            ("transcript", "TEXT", "''", True),  # 聞き取りのまま（Whisper の文字）
            ("error", "TEXT", "''", True),
            ("attempt", "INTEGER", "0", True),  # 再試行のたびに増やす。古い処理の結果は捨てる
            ("draft_id", "INTEGER", None, False),
            ("updated_at", "TEXT", "''", True),
            ("fix_off", "INTEGER", "0", True),  # 1=人が直した文字なので、聞き違いの自動の直しをしない
            ("deleted_at", "TEXT", None, False),  # 「この区切りを消す」を押した時刻。数秒だけ元に戻せる。そのあと音声と文字を消す
            ("prev_state", "TEXT", "''", True),  # 消す前の状態（元に戻すとき）
            ("role", "TEXT", "''", True),  # 録音したときの役割（doctor / hygienist）。空なら診療回の担当
            ("polished", "TEXT", "''", True),  # 聞き取りのすぐ後の清書（画面に出す文）。空なら清書していない（transcript は聞き取りのまま）
            ("polish", "TEXT", "'{}'", True),  # 清書のくわしい結果 {"fixes":[{from,to,by}], "doubts":[…], "note":"清書を使わなかった理由"}
        ],
        "extra": [_PATIENT_FK, _VISIT_FK],
    },
    # スマホで写真を受け渡すQR。トークンそのものは持たず、sha256 の値だけ置く。期限は epoch 秒。
    "phone_links": {
        "cols": [
            ("patient_id", "INTEGER", None, True),
            ("token_hash", "TEXT", None, True),
            ("created_at", "INTEGER", None, True),
            ("expires_at", "INTEGER", None, True),
        ],
        "extra": [_PATIENT_FK, "UNIQUE (token_hash)"],
    },
    # スマホで写真を入れた・取り出した時刻の記録（kind は 入れた / 取り出した）。
    "phone_events": {
        "cols": [
            ("link_id", "INTEGER", None, True),
            ("patient_id", "INTEGER", None, True),
            ("kind", "TEXT", None, True),
            ("photo_number", "INTEGER", None, False),
            ("at", "TEXT", None, True),
        ],
        "extra": [_PATIENT_FK],
    },
    # 声の聞き取りで後から直したいもの。患者様が決まっていない録音もあるので、診療回は空でもよい。
    "voice_fixes": {
        "cols": [
            ("patient_id", "INTEGER", None, False),
            ("visit_id", "INTEGER", None, False),
            ("heard", "TEXT", "''", True),
            ("note", "TEXT", "''", True),
            ("status", "TEXT", "'pending'", True),
            ("created_at", "TEXT", "''", True),
        ],
        "extra": [_VISIT_FK],
    },
}


def _col_sql(col, with_notnull=True):
    name, typ, default, notnull = col
    s = f"{name} {typ}"
    if with_notnull and notnull:
        s += " NOT NULL"
    if default is not None:
        s += f" DEFAULT {default}"
    return s


def create_sql(name):
    t = TABLES[name]
    parts = ["id INTEGER PRIMARY KEY"] + [_col_sql(c) for c in t["cols"]] + t["extra"]
    return f"CREATE TABLE {name} ({', '.join(parts)})"


def migrate(con: sqlite3.Connection):
    """足りない表と列を足す。あるデータは消さない。足した列の (表, 列) の一覧を返す。"""
    have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    added = []
    for name, t in TABLES.items():
        if name not in have:
            con.execute(create_sql(name))
            continue
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({name})")}
        for c in t["cols"]:
            if c[0] not in cols:
                con.execute(f"ALTER TABLE {name} ADD COLUMN {_col_sql(c, with_notnull=False)}")
                added.append((name, c[0]))
    return added
