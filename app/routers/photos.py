from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.views import photos as P

router = APIRouter()


@router.get("/photo-files/{name}")
def photo_file(name: str):
    """一覧（photos.json）にある画像だけ返す。"""
    if name not in {x["file"] for x in P.listing() + P.cards()}:
        raise HTTPException(404)
    path = P.photo_dir() / name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "no-store"})
