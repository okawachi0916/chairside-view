"""録音の区切り: この区切りを要約 / 今日の分をまとめて要約 / この区切りを消す・元に戻す。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.ai import recpipe, segview
from app.ai.recpipe import RecError
from app.db import connect

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}


def _json(data, status=200):
    return JSONResponse(data, status_code=status, headers=NO_STORE)


def _run(fn):
    con = connect()
    try:
        return _json(fn(con))
    except RecError as e:
        return _json({"error": str(e)}, e.status)
    finally:
        con.close()


class ApptBody(BaseModel):
    appt: int


@router.get("/api/segments")
def api_segments(appt: int):
    def go(con):
        recpipe.recover_stale(con)
        v = con.execute("SELECT id FROM visits WHERE appointment_id = ?", (appt,)).fetchone()
        vid = v["id"] if v else None
        return {"segments": segview.list_for_visit(con, vid), "combined_draft": segview.combined_draft(con, vid)}
    return _run(go)


@router.post("/rec/{rec_id}/summarize")
def rec_summarize(rec_id: int):
    return _run(lambda con: recpipe.summarize_segment(con, rec_id))


@router.post("/rec/combine")
def rec_combine(body: ApptBody):
    return _run(lambda con: recpipe.combine(con, body.appt))


@router.post("/rec/{rec_id}/delete")
def rec_delete(rec_id: int):
    return _run(lambda con: recpipe.delete_segment(con, rec_id))


@router.post("/rec/{rec_id}/undelete")
def rec_undelete(rec_id: int):
    return _run(lambda con: recpipe.undelete_segment(con, rec_id))
