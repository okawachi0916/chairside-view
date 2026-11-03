# 進捗 ai（AI 担当）

## 動く版
- 送信口 app/ai/gateway.py と伏字 app/ai/redact.py（直接 Claude を呼ぶのはここだけ）。モデルは config/model.json（目的ごとは purposes）。質問は Haiku、下書きは Sonnet
- 質問: POST /ai/ask（app/ai/ask.py）。前回・アレルギー・薬・次回は表（config/quick_answers.json）で直接、ほかは Claude が記録の番号を選ぶだけ。結果は docs/モデルの選び方.md
- 話した内容の下書き: 親の画面 /app で録音 → 転送 → 文字起こし → 聞き違いを直す（app/ai/fixtalk.py）→ 5つに分ける（memo.py）→ 下書き（recpipe.py）
  - ボタン1の文字起こしだけ initial_prompt（config/dental_terms.json、30語以内）。ボタン2の声には使わない
  - 聞き違い: Claude は {"from","to"} の一覧だけ返し、置き換えはプログラム。from が話に無い・数字が違う・長過ぎる直しは捨てる。迷う所は直さない。仮歯は TeC に統一（TEK などはルールで直す）
  - 話したままの文字は drafts.transcript、直した文字は fixed_transcript、直しの一覧は fixes。抜き出しの確認は直した文字に対して行う。人が直した文字（fix_off=1）は自動で直さない
  - 項目の文は句読点つき（文末は「。」）
- 下書きの画面 /drafts/{番号}?back=: ボタンは「カルテに記録する」「あとで直す」だけ。直した所は自動で保存（保存ボタンなし）。押すと来た画面（?back=、診療の画面・録音の一覧・今日の診療一覧）へ戻る。左上「戻る」と声の「戻して」は下書きのまま戻る。「確定する」→「確定」は今までどおり
  - 「治療計画の変更」は2つの列の下に全幅。話に出ていない計画は「そのまま残す」（削除は印なし）、新しい計画の「追加する」は印あり。表の名前を .rec から .rtab に変えた（見た目の .rec は右下に固定する録音中の札で、ぶつかっていた）
- 記録する: 診療メモ（clinical_notes）に入る。変更・削除した古い計画は superseded_on に日付で残す。音声は消す（app/ai/confirm.py）
- あとで直す: /fix/{録音}（音声・文字・再整理）。次の患者様の前で止める（actions/rec.js）。/today の印「大川内先生 追記必要」（押すと下書き）
- G26b: 点検係4つ（.claude/agents）、/review-all（docs/総点検.md）、コミット前の見張り .claude/hooks/commit_guard.py
- 試験: 全体 432 件（偽物の口）。送信文・伏字・応答・モデルを変えたら real_api_check.py の --questions、--memo、--fix を動かし直す

## 残り
- 録音は /app から開いたときだけ使える。実機のマイクでの通しは院長の確認待ち（試験は偽物のマイク）
- 録音1・2の文字は、院長の聞き違いの例から作り直した架空の文（実際の文字は手元に無い）。本物の録音の文字で確かめたい
- 初期の文を渡したとき数字が落ちないかの本物の確認は @pytest.mark.gpu（tests/test_fixtalk.py）。声の窓が動かす
- 治療歴は同じ日の診療メモがあると質問の記録に番号を付けない。電話・住所の列は DB に無い

## 次のゴール
- 指示待ち
