"""自由な質問への答え。聞き取った言葉を受け取り、記録の番号を Claude に選ばせ、本文はデータベースから返す。"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.ai import fake
from app.ai.ask import answer
from app.ai.gateway import Gateway
from app.db import connect

router = APIRouter()


def make_gateway() -> Gateway:
    """試験は make_gateway を差し替えるか、環境変数で偽物の口にする。"""
    return Gateway(mouth=fake.FileMouth()) if fake.fake_enabled() else Gateway()


class Ask(BaseModel):
    text: str = ""
    appt: int


@router.post("/ai/ask")
def ask(body: Ask):
    con = connect()
    try:
        row = con.execute("SELECT patient_id, appt_date FROM appointments WHERE id = ?", (body.appt,)).fetchone()
        if not row:
            raise HTTPException(404)
        res = answer(body.text, con, row["patient_id"], make_gateway(), visit_date=row["appt_date"])
    finally:
        con.close()
    return JSONResponse(res, headers={"Cache-Control": "no-store"})
