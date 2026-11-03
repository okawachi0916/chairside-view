# 進捗 ai（AI 担当）

## 動く版
- G14b/G15: 鍵と最新 Sonnet の設定、送信口 app/ai/gateway.py と伏字 app/ai/redact.py（直接 Claude を呼ぶのはここだけ）
- G16: 自由な質問への答え（POST /ai/ask、app/ai/ask.py）。質問10例は tests/questions.json
- G17: 話した内容を下書きにする。入口は親の画面 /app（録音と右下の窓）。流れは app/ai/recpipe.py、整理は app/ai/memo.py、画面は /recordings と /drafts/{番号}。話6通りは tests/memo_cases.json（本物の Claude でも全部合格）
- G19: 下書きの確定と後で直す
  - /drafts/{番号}: 5項目をキーボードで直す（足す・消す・書き換え）。「確定する」で過去の診療メモ（clinical_notes）に入る。確定前は何も入らない
  - 治療計画は今の計画と新しい計画を並べ、選んだ「変更・削除・追加」だけ反映。話に出ていない歯の計画は残る。古い計画は treatment_plans.superseded_on に日付を付けて残す
  - 声・文字: 「確定する」のあと「確定」（window.cvTyped、ボタン2）。確定したら音声を消す（app/ai/confirm.py）
  - 後で直す: 下書きのまま音声を残す。失敗（下書き無し）も音声と診療回を残して進める。直す画面は /fix/{録音}（音声・文字・再整理。新しい下書きは人が見てから確定）
  - 次の患者様へ進む前に「確定していない診療メモがあります」で止める（メモを開く／後で直す、actions/rec.js）
  - /today: 時間・カルテ番号・氏名（伏せ字）・処置・状態。確定していない人に「大川内先生 追記必要」が赤く点滅（確定で消える）。再起動しても残る
- 質問の速度改善（G16 の追加）: 前回・アレルギー・薬・次回のよく聞く質問は Claude を通さず記録から直接出す（app/ai/quick.py、言葉の表は config/quick_answers.json）。表の言葉とつなぎの言葉だけの短い質問にだけ当たり、ほかの言葉が混ざる質問・2項目にまたがる質問・記録が見つからない質問は Claude へ回す
  - モデルは目的ごと（config/model.json の purposes）。質問は claude-haiku-5-5、下書き（memo）は既定の Sonnet のまま。本物で Sonnet と Haiku の両方に G16 の問いを全部流し、Haiku も全問正解（約2.1秒→約1.3秒）なので採用。結果は docs/実API結果.md
  - 表を使わず Claude に聞く確認は real_api_check.py --questions --claude-only、質問だけ別モデルで試すのは --model 名前
- 試験: 全体 298 件（偽物の口）。送信文・伏字・応答・モデルを変えたら real_api_check.py の --questions と --memo を動かし直す

## 残り
- 録音は /app から開いたときだけ使える。実機のマイクでの通しは院長の確認待ち（試験は偽物のマイク）
- 追記必要の印は、録音を始めた診療回の予約の行に付く
- 治療歴は同じ日の診療メモがあると質問の記録に番号を付けない。電話・住所の列は DB に無い

## 次のゴール
- 指示待ち（G20 以降は指示を確認）
