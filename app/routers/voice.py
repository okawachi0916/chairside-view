import json
import threading
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.voice import transcribe as tr

router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]


def _warm():
    """最初の1回を速くするため、起動時に裏でモデルを読んでおく。読めなくても起動は続ける。"""
    try:
        tr._model(tr.settings()["model"])
    except Exception:
        pass


threading.Thread(target=_warm, daemon=True).start()


@router.get("/config/keys.json")
def keys():
    return json.loads((ROOT / "config" / "keys.json").read_text(encoding="utf-8"))


@router.get("/voice-test", response_class=HTMLResponse)
def voice_test():
    return (ROOT / "app" / "voice" / "voice_test.html").read_text(encoding="utf-8")


@router.post("/voice/transcribe")
async def transcribe(request: Request):
    data = await request.body()
    try:
        audio = tr.to_pcm(data)
    except Exception as e:
        return JSONResponse({"stage": "audio", "error": f"録音を音声に戻せませんでした（{e}）"}, status_code=400)
    try:
        return tr.transcribe(audio)
    except Exception as e:
        return JSONResponse({"stage": "transcribe", "error": f"文字起こしに失敗しました（{e}）"}, status_code=500)
