"""本物の Claude を呼んで確かめる（普段の試験では動かさない）。

使い方:
  python scripts/real_api_check.py            モデル一覧→最新の Sonnet を config/model.json に書く→短文を1回送る
  python scripts/real_api_check.py --no-write モデル名を書き換えず、今の設定で送るだけ
結果は docs/実API結果.md に追記する。鍵は出力にも記録にも出さない。
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import anthropic  # noqa: E402

from app.ai.settings import ClaudeUnavailable, load_key, load_model, redact_key, MODEL_JSON  # noqa: E402

RESULT_MD = ROOT / "docs" / "実API結果.md"
PROMPT = "こんにちは。1文で返事をしてください。"


def newest_sonnet(client) -> str:
    # 一覧は新しい順で返る。名前に sonnet を含むものの先頭を取る。
    names = [m.id for m in client.models.list(limit=100) if "sonnet" in m.id.lower()]
    if not names:
        raise SystemExit("使える Sonnet が一覧に見つかりません")
    return names[0]


def commit_id() -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "不明"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    try:
        client = anthropic.Anthropic(api_key=load_key())  # 鍵は明示して渡す。ANTHROPIC_API_KEY は使わない
    except ClaudeUnavailable as e:
        print(e)
        return 2
    try:
        if not args.no_write:
            model = newest_sonnet(client)
            MODEL_JSON.parent.mkdir(exist_ok=True)
            MODEL_JSON.write_text(json.dumps({"model": model}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        model = load_model()
        res = client.messages.create(model=model, max_tokens=100, messages=[{"role": "user", "content": PROMPT}])
        text = "".join(b.text for b in res.content if getattr(b, "type", "") == "text")
        ok = bool(text.strip())
    except Exception as e:  # noqa: BLE001
        print("失敗:", redact_key(f"{type(e).__name__}: {e}")[:200])
        return 1
    print("モデル:", model)
    print("応答:", redact_key(text)[:100])
    RESULT_MD.parent.mkdir(exist_ok=True)
    if not RESULT_MD.exists():
        RESULT_MD.write_text("# 実API結果\n\n本物の Claude を呼んだ確認の記録。\n", encoding="utf-8")
    with RESULT_MD.open("a", encoding="utf-8") as f:
        f.write(
            f"\n## {datetime.now():%Y-%m-%d %H:%M} 接続の確認\n"
            f"- コミット: {commit_id()}\n- モデル: {model}\n- 入力: {PROMPT}\n"
            f"- 判定: {'合格（応答あり）' if ok else '不合格（応答が空）'}\n"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
