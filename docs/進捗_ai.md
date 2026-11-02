# 進捗 ai（AI 担当）

## 動く版
- G14b: app/ai/settings.py（鍵は環境変数 CHAIRSIDE_CLAUDE_KEY、無ければ app.env の同名の行。ANTHROPIC_API_KEY は見ない）
- config/model.json に最新 Sonnet の名前。プログラムには書かない。scripts/real_api_check.py で本物を1回確認済み。
- G15: Claude へ送るのは app/ai/gateway.py の Gateway.send だけ（anthropic の読み込みもここだけ）
  - app/ai/redact.py: 氏名・姓・名・読み・番号・電話・住所・生年月日・職員・医院を伏字。長い順、送信ごとに別の表、残りがあれば RedactionFailed
  - 送った文（伏字のもの）は data/runtime/sent_log/日付.jsonl
- 試験: tests/test_ai_connect.py、tests/test_ai_gateway.py（偽物の口。計49件）

## 残り
- 伏字の対象に電話・住所を入れるデータが DB に無い（Patient に渡せば効く）。実データ化は別ゴール
- 送信文・伏字を変えたら real_api_check.py の再実行が要る（今回は送信文を変えていないので未実行）

## 次のゴール
- G16 以降（指示を確認）
