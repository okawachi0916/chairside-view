"""見本の画面。動かない見本で、中身は画面に直接書いてある。"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.mockview import booklist, doctor, hygienist, reception

router = APIRouter(prefix="/mock")


@router.get("/doctor", response_class=HTMLResponse)
def mock_doctor():
    return doctor.render()


@router.get("/hygienist", response_class=HTMLResponse)
def mock_hygienist():
    return hygienist.render()


@router.get("/reception", response_class=HTMLResponse)
def mock_reception():
    return reception.render()


@router.get("/", response_class=HTMLResponse)
def mock_list():
    return booklist.render()
