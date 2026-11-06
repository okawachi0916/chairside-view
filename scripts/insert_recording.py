"""動画の撮影用。保存してある音声（院長の録音）を、患者様の今日の診療回に、ボタン1で録ったときと同じ形で録音1本として入れ、
本番と同じ道（文字起こし → 清書 → 「今日の分をまとめて要約」）で下書きまで作る。
  python scripts/insert_recording.py 音声ファイル カルテ番号 [役割 doctor] [秒数]
音声ファイルは動かさず、写して使う（data/runtime/audio/rec_番号.webm）。録音の行は1本だけ。
データは data/runtime（環境変数 CV_DATA_DIR があればそちら）。Claude と文字起こしは本番と同じ道（鍵とモデルは使うときに読む）。"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.ai import recpipe  # noqa: E402
from app.db import connect  # noqa: E402
from app.today import today  # noqa: E402
from redo_recording import wait_for  # noqa: E402


def main(argv) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    src, chart = Path(argv[1]), argv[2]
    role = argv[3] if len(argv) > 3 else "doctor"
    dur = float(argv[4]) if len(argv) > 4 else 0.0
    if not src.is_file():
        raise SystemExit(f"音声ファイルがありません: {src}")
    con = connect()
    try:
        a = con.execute("SELECT a.id FROM appointments a JOIN patients p ON p.id = a.patient_id WHERE p.chart_no = ? AND a.appt_date = ? "
                        "AND a.role = ? AND a.status IN ('booked', 'done') ORDER BY a.start_time", (chart, today(), role)).fetchone()
        if not a:
            raise SystemExit(f"カルテ番号 {chart} の今日の予約（{role}）がありません")
        if con.execute("SELECT 1 FROM recordings WHERE state NOT IN (?, ?) LIMIT 1", (recpipe.DELETED, recpipe.CONFIRMED)).fetchone():
            raise SystemExit("録音がすでにあります。見本の状態へ戻してから入れてください（録音の行は1本だけにします）")
        r = recpipe.start(con, a["id"], role)
        recpipe.save_audio(con, r["id"], src.read_bytes(), dur)   # 写して使う。元の音声は動かさない
        t0 = time.time()
        recpipe.transfer(con, r["id"])
        print("文字起こし・清書中…")
        wait_for(r["id"], (recpipe.SEGMENT,), "文字起こし")
        t1 = time.time()
        recpipe.combine(con, a["id"], role)
        print("要約中…")
    finally:
        con.close()
    r = wait_for(r["id"], (recpipe.DRAFT,), "要約")
    con = connect()
    try:
        d = con.execute("SELECT * FROM drafts WHERE id = ?", (r["draft_id"],)).fetchone()
        print(f"録音 {r['id']} 下書き {d['id']}（文字起こしと清書 {t1 - t0:.1f}秒、まとめの要約 {time.time() - t1:.1f}秒）")
        print("直した聞き違い:", [(f["from"], f["to"]) for f in json.loads(d["fixes"])])
        print("迷う印:", json.loads(d["doubts"]))
        print("聞き取りのまま:", d["transcript"])
        print("清書:", d["fixed_transcript"])
        print("下書き:", d["body"].replace(chr(10), " / "))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
