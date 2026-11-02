# 進捗 ai（AI 担当）

## 動く版
- G14b/G15: 鍵と最新 Sonnet の設定、送信口 app/ai/gateway.py と伏字 app/ai/redact.py（直接 Claude を呼ぶのはここだけ）
- G16: 自由な質問への答え
  - POST /ai/ask（app/routers/ai.py）→ app/ai/ask.py。G13 で「質問」と分けた言葉だけ送る（無関係・聞き取り失敗・操作は0回）
  - 記録は app/ai/records.py で番号付け（患者番号×100+1 から）。Claude は {"result":"found","record":番号} / none / unclear のどれかを返すだけ
  - 形の違う応答・渡していない番号・別の患者様の番号は捨てて「もう一度お願いします」。本文はデータベースの文字そのまま
  - 画面: app/static/js/actions/ai.js（周りを暗く、縦長の枠、出どころ、もとに戻す／戻して）。患者様が変わったら遅れた答えは捨てる
  - 質問10例は tests/questions.json に固定
- 試験: 全体 202 件（偽物の口）。本物の Claude 9問は 9問とも正解（docs/実API結果.md、10例目は送信0回）
- 偽物の口: tests/conftest.py が環境変数 CHAIRSIDE_AI_FAKE_FILE を設定。答えはそのファイルを書き換えて変える

## 残り
- 治療歴は同じ日の診療メモがあると記録の番号を付けない（正解が2つに割れるため）
- 電話・住所の列は DB に無い（伏字は渡されたときだけ効く）
- 送信文・伏字・応答の処理を変えたら real_api_check.py --questions を動かし直す

## 次のゴール
- 指示待ち
