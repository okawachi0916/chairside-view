"""サーバーを起動したとき、データベースを用意して、見本の日付を今日へ合わせる（app/db/dates.py の決まり）。"""
import logging

from fastapi import APIRouter

from app import errlog
from app.views import data as D

router = APIRouter()
LOG = logging.getLogger("chairside.startup")


def _prepare():
    try:
        D.con().close()  # 無ければ作り、足りない分を足し、日付を今日へ合わせる。あとは開くたびに通る
    except Exception as e:  # noqa: BLE001  起動は続ける。最初の画面の読み込みで同じ処理がもう一度動く
        LOG.exception("起動時のデータベースの用意に失敗しました")
        errlog.record("起動", "データベースを用意できませんでした", e)


router.add_event_handler("startup", _prepare)
