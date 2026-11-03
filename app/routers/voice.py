import json
import logging
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.voice import transcribe as tr
from app.voice.interpret import interpret, load_table

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


@router.post("/voice/interpret")
async def interpret_text(request: Request):
    """聞き取った言葉を手元で照合する（Claude は使わない）。"""
    body = await request.json()
    return JSONResponse(interpret(str(body.get("text") or ""), str(body.get("screen") or "unit")))


@router.get("/voice/commands")
def commands():
    """「いま言える言葉」の一覧。状態が「使える」の行だけ返す。"""
    return {"words": [r["言葉"] for r in load_table()
                      if r["状態"] == "使える" and "(" not in r["言葉"] and r["結果"].get("action") != "part-number"]}


@router.get("/voice/examples")
def examples():
    """暗い画面に出す例文。画面ごとの表（config/examples.json）。"""
    return json.loads((ROOT / "config" / "examples.json").read_text(encoding="utf-8"))


@router.get("/voice/numbers")
def numbers():
    """画面の丸の番号。部品ごとに固定（config/numbers.json）。"""
    return json.loads((ROOT / "config" / "numbers.json").read_text(encoding="utf-8"))


LOG = logging.getLogger("uvicorn.error")


@router.post("/voice/timing")
async def timing(request: Request):
    """声のあと画面が変わるまでの時間を、1行だけログへ残す（data/runtime/logs/voice_timing.log と画面のログ）。"""
    try:
        b = await request.json()
        parts = {k: int(b.get(k) or 0) for k in ("transcribe_ms", "interpret_ms", "apply_ms", "total_ms", "mic_ms")}
    except Exception:
        return JSONResponse({"error": "形が違います"}, status_code=400)
    line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} 声の時間 文字起こし {parts['transcribe_ms']}ms"
            f" / 判定 {parts['interpret_ms']}ms / 画面の反映 {parts['apply_ms']}ms / 合計 {parts['total_ms']}ms"
            f" / 録音の開始 {parts['mic_ms']}ms / 判定の種類 {str(b.get('kind') or '')[:8]}")
    LOG.info(line)
    try:
        d = ROOT / "data" / "runtime" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "voice_timing.log", "a", encoding="utf-8") as f:
            f.write(line + chr(10))
    except OSError:
        pass
    return {"ok": True, "line": line}
