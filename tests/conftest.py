import json
import os
import tempfile
from pathlib import Path


def pytest_configure(config):
    # 見本の「今日」は試験では 2026-11-06 に止める（既存の試験の日付を保つ）。日付をずらす試験は自分で CV_TODAY を指す
    os.environ.setdefault("CV_TODAY", "2026-11-06")
    config.addinivalue_line("markers", "gpu: GPU を使う試験（merge_lane.py は動かさない。声の窓だけが動かす）")
    # 普段の試験は本物の Claude を呼ばない。サーバーが起動時に引き継ぐ環境変数で、偽物の口に固定する。
    # 偽物の答えは、このファイルを書き換えて変える（既定は「分からない」）。
    f = Path(tempfile.gettempdir()) / f"cv_ai_fake_{os.environ.get('CV_PORT', '8840')}.json"
    f.write_text(json.dumps({"reply": '{"result":"unclear"}', "delay_ms": 0}), encoding="utf-8")
    os.environ["CHAIRSIDE_AI_FAKE_FILE"] = str(f)
    # スマホ用のサーバーは、試験では自分で動かす（メインの試験サーバーが 8841 を取らないように）。ポートは 8861
    os.environ["CV_MOBILE_AUTOSTART"] = "0"
    os.environ["CV_MOBILE_PORT"] = "8861"
    # QR のアドレスは、試験では public_url.txt を読まず院内のアドレスにする（試験用のファイルは試験が指定する）
    os.environ.setdefault("CV_PUBLIC_URL_FILE", str(Path(tempfile.gettempdir()) / "cv_no_public_url.txt"))
    # 既存の試験は「止めたら要約まで」を前提にしている。G19b の新しい試験だけ、既定（要約は自動で作らない）に戻して調べる
    os.environ.setdefault("CHAIRSIDE_AUTO_SUMMARY", "1")
