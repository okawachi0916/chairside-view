"""動画の撮影用。録音1つを、文字起こしからやり直し、その診療回の「今日の分をまとめて要約」と同じ下書きを作り直す。
  python scripts/redo_recording.py 録音の番号 [役割]
音声（audio の rec_N.webm）はそのまま使う。録音の行・下書きの行は増やさず、同じ録音の結果を置き換える。
データは data/runtime（環境変数 CV_DATA_DIR があればそちら）。Claude と文字起こしは、本番と同じ道（鍵とモデルは使うときに読む）。"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai import recpipe  # noqa: E402
from app.db import connect  # noqa: E402

WAIT_SEC = 300


def wait_for(rec_id: int, states, what: str):
    end = time.time() + WAIT_SEC
    while time.time() < end:
        con = connect()
        try:
            r = recpipe.get(con, rec_id)
        finally:
            con.close()
        if r["state"] in states:
            return r
        if r["state"] == recpipe.FAILED:
            raise SystemExit(f"{what}で失敗しました: {r['error']}")
        time.sleep(1)
    raise SystemExit(f"{what}が{WAIT_SEC}秒で終わりません")


def main(argv) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    rec_id, role = int(argv[1]), (argv[2] if len(argv) > 2 else "doctor")
    con = connect()
    try:
        r = recpipe.get(con, rec_id)
        if not r or not r["audio_file"]:
            raise SystemExit("その録音が無いか、音声がありません")
        a = con.execute("SELECT appointment_id FROM visits WHERE id = ?", (r["visit_id"],)).fetchone()
        if not a:
            raise SystemExit("その録音の診療回が見つかりません")
        # 文字を空にして「後で直す」へ戻し、再試行（= 文字起こしからの道）に乗せる。ほかの行は触らない
        con.execute("UPDATE recordings SET transcript = '', fix_off = 0, state = ?, error = '', updated_at = ? WHERE id = ?",
                    (recpipe.LATER, recpipe.now(), rec_id))
        con.commit()
        recpipe.retry(con, rec_id)
        print("文字起こし中…")
        wait_for(rec_id, (recpipe.SEGMENT,), "文字起こし")
        recpipe.combine(con, a["appointment_id"], role)
        print("要約中…")
    finally:
        con.close()
    r = wait_for(rec_id, (recpipe.DRAFT,), "要約")
    con = connect()
    try:
        d = con.execute("SELECT * FROM drafts WHERE id = ?", (r["draft_id"],)).fetchone()
        import json
        print("下書き", d["id"], "直した聞き違い:", [(f["from"], f["to"]) for f in json.loads(d["fixes"])])
        print("直した文字:", d["fixed_transcript"])
        print("下書き:", d["body"].replace(chr(10), " / "))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
