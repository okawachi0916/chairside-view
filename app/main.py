"""チェアサイドビュー本体。app/routers の中のファイルを自動で読み込む。"""
import importlib
import pkgutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import routers

app = FastAPI(title="チェアサイドビュー")

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

for _m in pkgutil.iter_modules(routers.__path__):
    _mod = importlib.import_module(f"app.routers.{_m.name}")
    if hasattr(_mod, "router"):
        app.include_router(_mod.router)
