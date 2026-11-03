"""動画の撮影用。data/runtime の中身 (データベース、下書き、音声、追記必要の印など) を丸ごと写し、あとで戻す。
  python scripts/demo_state.py save 名前      写す
  python scripts/demo_state.py restore 名前   全部を戻し、そのあと scripts/update_db.py を動かす
写す先は環境変数 CV_DEMO_DIR、無ければ C:\\hackathon\\demo_states。名前ごとのフォルダに入る。
写す先はリポジトリの外で、Git に入れない。サーバーが動いたままでも戻せる。"""
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import data_dir, db_path  # noqa: E402

DEFAULT_DEMO_DIR = r"C:\hackathon\demo_states"
DB_NAME = "app.db"
SIDE = ("-wal", "-shm", "-journal")


def demo_dir() -> Path:
    return Path(os.environ.get("CV_DEMO_DIR") or DEFAULT_DEMO_DIR)


def state_dir(name: str) -> Path:
    if not re.fullmatch(r"[0-9A-Za-z_\-ぁ-んァ-ヶ一-龠]+", name or ""):
        raise SystemExit("名前には文字・数字・_・- だけを使ってください")
    return demo_dir() / name


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _copy_db(src: Path, dst: Path):
    """動いているデータベースでも整った形で写す (SQLite の backup)。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    a = sqlite3.connect(src, timeout=30)
    b = sqlite3.connect(dst, timeout=30)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


def _entries(d: Path):
    return [p for p in d.iterdir() if not (p.name.startswith(DB_NAME) and p.name != DB_NAME)] if d.exists() else []


def save(name: str) -> Path:
    src, dst = data_dir(), state_dir(name)
    if _is_inside(dst, src) or _is_inside(src, dst):
        raise SystemExit("写す先と data/runtime が重なっています")
    if not db_path().exists():
        raise SystemExit(f"{db_path()} がありません。先にサーバーを一度動かすか scripts/seed.py を動かしてください")
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for p in _entries(src):
        if p.name == DB_NAME:
            _copy_db(p, dst / DB_NAME)
        elif p.is_dir():
            shutil.copytree(p, dst / p.name)
        else:
            shutil.copy2(p, dst / p.name)
    return dst


def restore(name: str) -> Path:
    src, dst = state_dir(name), data_dir()
    if not (src / DB_NAME).exists():
        raise SystemExit(f"{src} に写した物がありません。名前を確かめてください")
    dst.mkdir(parents=True, exist_ok=True)
    keep = {p.name for p in _entries(src)}
    for p in _entries(dst):  # 写した時に無かった物は消す (増えた下書きや音声)
        if p.name not in keep:
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    for p in _entries(src):
        t = dst / p.name
        if p.name == DB_NAME:
            _copy_db(p, t)
        elif p.is_dir():
            shutil.rmtree(t, ignore_errors=True)
            shutil.copytree(p, t)
        else:
            shutil.copy2(p, t)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "update_db.py")], cwd=ROOT, env=os.environ.copy())
    if r.returncode != 0:
        raise SystemExit("戻したあとの update_db.py が失敗しました")
    return dst


def main(argv):
    if len(argv) != 3 or argv[1] not in ("save", "restore"):
        print(__doc__)
        return 2
    d = save(argv[2]) if argv[1] == "save" else restore(argv[2])
    print(("写しました: " if argv[1] == "save" else "戻しました: ") + str(d))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
