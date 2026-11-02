"""data/runtime を初期の状態へ戻す。何回動かしても同じ件数、同じ写真番号になる。
写真の画像 (data/runtime/photos) は消さない。"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import data_dir, db_path  # noqa: E402
from app.db.update import update  # noqa: E402

# 実行時に増える物。写真の画像 (photos) は入れない。
RESET_DIRS = ["drafts", "recordings", "outbox"]


def main():
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = db_path()
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(str(p) + suffix).unlink(missing_ok=True)
    for name in RESET_DIRS:
        shutil.rmtree(d / name, ignore_errors=True)
    r = update(p)
    print(f"{p}: 行 {sum(r['inserted'].values())} 件を入れました")


if __name__ == "__main__":
    main()
