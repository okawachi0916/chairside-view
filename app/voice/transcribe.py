"""録音データ（webm など）を 16kHz モノラルの配列にして faster-whisper で文字にする。音声は保存しない。"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

CONFIG = Path(__file__).resolve().parents[2] / "config" / "voice.json"
_models = {}


def settings():
    d = {"model": "large-v3", "cache_dir": os.environ.get("CV_CACHE", r"C:\hackathon\work\_cache") + "\\whisper"}
    if CONFIG.exists():
        d.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return d


def to_pcm(data: bytes) -> np.ndarray:
    """ffmpeg に標準入力で渡し、16kHz モノラル float32 の配列で受け取る（ファイルは作らない）。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg が見つかりません")
    r = subprocess.run(
        [ffmpeg, "-v", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", "16000", "pipe:1"],
        input=data, capture_output=True,
    )
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("録音を音声に戻せません")
    return np.frombuffer(r.stdout, dtype=np.float32)


def _model(name: str):
    if name not in _models:
        from faster_whisper import WhisperModel
        cache = settings()["cache_dir"]
        try:
            _models[name] = WhisperModel(name, device="cuda", compute_type="float16", download_root=cache)
        except Exception:
            _models[name] = WhisperModel(name, device="cpu", compute_type="int8", download_root=cache)
    return _models[name]


def transcribe(audio: np.ndarray, model: str | None = None, initial_prompt: str | None = None) -> dict:
    """initial_prompt は、ボタン1の録音の文字起こしだけが渡す（歯科の短い一文と主な語）。ボタン2の声の指示には渡さない。"""
    name = model or settings()["model"]
    m = _model(name)
    t0 = time.perf_counter()
    extra = {"initial_prompt": initial_prompt} if initial_prompt else {}
    segs, _ = m.transcribe(audio, language="ja", beam_size=1, vad_filter=False, **extra)
    text = "".join(s.text for s in segs).strip()
    return {"text": text, "model": name, "seconds": round(time.perf_counter() - t0, 2)}
