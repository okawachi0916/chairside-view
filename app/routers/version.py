"""今の版の印。開いている画面が30秒ごとに見て、開いたときの版と違えば「更新」のボタンを出す。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import versioning

router = APIRouter()


@router.get("/version")
def version():
    return JSONResponse(versioning.current(), headers={"Cache-Control": "no-store"})
