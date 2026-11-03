"""python -m app.mobile でスマホ用のサーバーだけを動かす。ポートは環境変数 CV_MOBILE_PORT、無ければ 8841。"""
import uvicorn

from app.mobile import links
from app.mobile.server import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=links.mobile_port(), log_level="warning")
