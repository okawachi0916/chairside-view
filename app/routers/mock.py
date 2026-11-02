"""見本の画面。動かない見本で、中身は画面に直接書いてある。"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.mockview import doctor

router = APIRouter(prefix="/mock")


@router.get("/doctor", response_class=HTMLResponse)
def mock_doctor():
    return doctor.render()
