"""本物の画面の入口。/ が予約一覧、/unit がユニットの画面、/reception が受付の画面。
画面の中身は毎回データベースから読み、ブラウザには保存させない。"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from app.views import data as D
from app.views import render as R

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}


def _html(s):
    return HTMLResponse(s, headers=NO_STORE)


def _json(html, role, title):
    return JSONResponse({"html": html, "role": role, "title": title}, headers=NO_STORE)


@router.get("/", response_class=HTMLResponse)
def appointment_list():
    return _html(R.list_page(D.today_list()))


@router.get("/unit", response_class=HTMLResponse)
def unit():
    return _html(R.shell("unit", "ユニットの画面"))


@router.get("/reception", response_class=HTMLResponse)
def reception():
    return _html(R.shell("reception", "受付の画面"))


@router.get("/api/view/unit")
def unit_view(appt: int, role: str = ""):
    a = D.appointment(appt)
    if not a:
        raise HTTPException(404)
    if role not in D.ROLE_NAME:
        role = a["role"] if a["role"] in D.ROLE_NAME else "doctor"
    d = D.unit_data(a, role)
    if role == "hygienist":
        return _json(R.hygienist_page(d), role, "歯科衛生士の画面")
    return _json(R.doctor_page(d), role, "歯科医師の画面")


@router.get("/api/view/reception")
def reception_view(patient: int = 0):
    if not patient:
        return _json(R.reception_chooser(D.reception_patients()), "reception", "受付の画面")
    ids = {p["id"] for p in D.reception_patients()}
    if patient not in ids:
        raise HTTPException(404)
    return _json(R.reception_page(D.reception_data(patient)), "reception", "受付の画面")
