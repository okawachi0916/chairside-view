from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index():
    return "<!doctype html><html lang='ja'><meta charset='utf-8'><title>チェアサイドビュー</title><body><h1>準備OK</h1></body></html>"
