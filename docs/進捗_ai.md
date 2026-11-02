# 進捗 ai（AI 担当）

## 動く版
- G14b/G15: 鍵と最新 Sonnet の設定、送信口 app/ai/gateway.py と伏字 app/ai/redact.py（直接 Claude を呼ぶのはここだけ）
- G16: 自由な質問への答え（POST /ai/ask、app/ai/ask.py、actions/ai.js）。質問10例は tests/questions.json
- G17: 話した内容を下書きにする
  - 入口は親の画面 /app（録音と右下の窓を持ち、中の画面だけ替える）。ボタン1（REC）で録音、もう一度で止める
  - 録音の窓は app/static/js/rec.js。患者様・診療回は始めたときに固定。固定中は次の患者様へ進めない（actions/rec.js）
  - ボタン2の声の指示の間は録音を一時停止（voice.js から CVRec.hold）。OK は画面でも REC 1回でも可。30秒で転送待ち
  - 流れは app/ai/recpipe.py（録音中→転送待ち→文字起こし中→整理中→下書き／失敗・後で直す）。音声は data/runtime/audio に先に保存
  - 整理は app/ai/memo.py（5つに分け、抜き出しが話の中に無い行は出さない）。画面は /recordings と /drafts/{番号}
  - 失敗は理由と再試行。再起動のあとも保存した音声から再試行でき、下書きは1録音に1つ
  - 文字を貼り付ける口は /recordings の下の欄（POST /rec/paste）
- 試験: 全体 240 件（偽物の口）。tests/memo_cases.json の6通りは本物の Claude でも全部合格（docs/実API結果.md）
- 偽物の口: tests/conftest.py の CHAIRSIDE_AI_FAKE_FILE（reply と transcript を書き換えて変える）

## 残り
- 録音は /app から開いたときだけ使える（直接 /unit を開くと「録音は /app から」と出る）
- 治療歴は同じ日の診療メモがあると質問の記録に番号を付けない。電話・住所の列は DB に無い
- 確定は G18。実機のマイクでの通しは院長の確認待ち（試験は偽物のマイク）
- 送信文・伏字・応答を変えたら real_api_check.py の --questions と --memo を動かし直す

## 次のゴール
- G18（確定と、後で直す）
