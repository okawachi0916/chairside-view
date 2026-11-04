"""撮影の前に、院長が試しに入れたものを消して見本の状態へ戻す。
  python scripts/reset_for_shoot.py
1. 今のデータベースを、日付つきの名前で控えに残す（C:\hackathon\demo_states\db_backups、環境変数 CV_DEMO_DIR で変更）
2. scripts/seed.py と同じ手順で、データベース・下書き・録音・音声を見本の状態へ戻す（写真の画像は残す）
サーバーは動いたままでよい。"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db import db_path  # noqa: E402
from demo_state import demo_dir  # noqa: E402
import seed  # noqa: E402


def backup() -> Path | None:
    p = db_path()
    if not p.exists():
        return None
    out = demo_dir() / "db_backups"
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"app_{datetime.now():%Y%m%d_%H%M%S}.db"
    src = sqlite3.connect(p, timeout=30)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)  # 動いているデータベースでも一貫した写しになる
    finally:
        dst.close()
        src.close()
    return dest


def main():
    dest = backup()
    print("控え:", dest if dest else "（データベースがまだ無いので控えは作りませんでした）")
    seed.main()
    print("見本の状態へ戻しました。")


if __name__ == "__main__":
    main()
