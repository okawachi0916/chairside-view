# 進捗 ai（AI 担当）

## 動く版
- G14b: app/ai/settings.py（鍵は環境変数 CHAIRSIDE_CLAUDE_KEY、無ければ app.env の同名の行。ANTHROPIC_API_KEY は見ない）
- config/model.json に最新 Sonnet の名前（claude-sonnet-5-5）。プログラムには書かない。
- scripts/real_api_check.py: 一覧→model.json 更新→短文を1回送る→docs/実API結果.md に記録。応答あり。
- 試験: tests/test_ai_connect.py（偽物のみ）

## 残り
- G15 送信の1か所化と伏字

## 次のゴール
- G15
