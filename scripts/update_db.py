"""データベースが無ければ seed.py と同じ状態で作る。あれば足りない表と列を足し、
写真と初期データの行は無ければ足す。あるデータは消さない。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import db_path  # noqa: E402
from app.db.update import update  # noqa: E402

if __name__ == "__main__":
    r = update()
    print(f"{db_path()}: 足した列 {len(r['added_columns'])}、足した行 {sum(r['inserted'].values())}")
