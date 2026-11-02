import json
import os
import tempfile
from pathlib import Path


def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: GPU を使う試験（merge_lane.py は動かさない。声の窓だけが動かす）")
    # 普段の試験は本物の Claude を呼ばない。サーバーが起動時に引き継ぐ環境変数で、偽物の口に固定する。
    # 偽物の答えは、このファイルを書き換えて変える（既定は「分からない」）。
    f = Path(tempfile.gettempdir()) / f"cv_ai_fake_{os.environ.get('CV_PORT', '8840')}.json"
    f.write_text(json.dumps({"reply": '{"result":"unclear"}', "delay_ms": 0}), encoding="utf-8")
    os.environ["CHAIRSIDE_AI_FAKE_FILE"] = str(f)
