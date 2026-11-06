"""G29: 審査の方がほかの PC で動かすときに困らないこと。
- 文字起こしのモデルが手元に無いとき、起動で数GBを勝手に取りにいかない（使うときに取得する）
- モデルの置き場は、環境変数 CV_CACHE、無ければ作品のフォルダの隣の _cache"""
from pathlib import Path

from app.routers import voice as voice_router
from app.voice import transcribe as tr

ROOT = Path(__file__).resolve().parents[1]


def test_cache_default_is_next_to_the_repo(monkeypatch):
    monkeypatch.delenv("CV_CACHE", raising=False)
    assert Path(tr.settings()["cache_dir"]) == ROOT.parent / "_cache" / "whisper"
    monkeypatch.setenv("CV_CACHE", str(ROOT / "x"))
    assert Path(tr.settings()["cache_dir"]) == ROOT / "x" / "whisper"


def test_no_model_in_cache_means_no_warmup_download(monkeypatch, tmp_path):
    monkeypatch.setenv("CV_CACHE", str(tmp_path))
    assert tr.model_is_cached("large-v3") is False
    called = []
    monkeypatch.setattr(tr, "_model", lambda name: called.append(name))
    voice_router._warm()
    assert called == []  # 取得を始めない


def test_cached_model_is_warmed_up(monkeypatch):
    called = []
    monkeypatch.setattr(tr, "model_is_cached", lambda name: True)
    monkeypatch.setattr(tr, "_model", lambda name: called.append(name))
    voice_router._warm()
    assert called == [tr.settings()["model"]]
