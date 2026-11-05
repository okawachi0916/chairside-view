# 進捗 ai（AI 担当）
## 動く版
- 送信口 app/ai/gateway.py と伏字 app/ai/redact.py（直接 Claude を呼ぶのはここだけ）。モデルは config/model.json（目的ごとは purposes）。質問は Haiku、下書きは Sonnet
- 質問: POST /ai/ask（app/ai/ask.py）。前回・アレルギー・薬・次回は表（config/quick_answers.json）で直接、ほかは Claude が記録の番号を選ぶだけ。結果は docs/モデルの選び方.md
- 話した内容の下書き: 親の画面 /app で録音 → 転送 → 文字起こし → 聞き違いを直す（app/ai/fixtalk.py）→ 5つに分ける（memo.py）→ 下書き（recpipe.py）
  - ボタン1の文字起こしだけ initial_prompt（config/dental_terms.json、30語以内）。ボタン2の声には使わない
  - 清書（G19k）: 聞き取りのすぐ後に Claude が文脈（今日の予約・治療計画・治療歴＋glossary）から聞き違いを直した全文を返す（fixtalk.polish）。画面の本文は清書（下線・迷う印）、聞き取りのままは押すと開く。安全策は数字が変わる・1.3倍超の2つだけ（捨てて聞き取りのまま＋理由）。失敗しても止めない。readings は聞き違いの例として渡すだけ。モデルは purposes.polish（Sonnet。docs/清書のモデル比べ.md）。録音の列 polished/polish、下書きの列 doubts/polish_note
  - 聞き取りのままは recordings.transcript と drafts.transcript、清書は recordings.polished と drafts.fixed_transcript、直しの一覧は fixes。人が直した文字（fix_off=1）は清書しない
  - 項目の文は句読点つき（文末は「。」）
- 下書きの画面 /drafts/{番号}?back=: ボタンは「カルテに記録する」「あとで直す」だけ。直した所は自動で保存（保存ボタンなし）。押すと来た画面（?back=、診療の画面・録音の一覧・今日の診療一覧）へ戻る。左上「戻る」と声の「戻して」は下書きのまま戻る。G19g: ボタン2で番号の札（numtags.js＝声の窓の札を取り出した共用。カルテに記録する・あとで直す・消す・削除する・整理し直す・戻る）。言葉は「カルテに記録する」→「記録」（または「確定する」→「確定」）、「あとで直す」「戻して」、敬語も可。「言える言葉」の黒い帯（ボタン2か画面右上の「言える言葉」ボタン。中身は examples.json の draft）に出ている言葉だけが動く。使えない言葉は「ボタン2で番号を出して選べます」
  - 「治療計画の変更」は2つの列の下に全幅。話に出ていない計画は「そのまま残す」（削除は印なし）、新しい計画の「追加する」は印あり。表の名前を .rec から .rtab に変えた（見た目の .rec は右下に固定する録音中の札で、ぶつかっていた）
- 記録する: 診療メモ（clinical_notes）に入る。変更・削除した古い計画は superseded_on に日付で残す。音声は消す（app/ai/confirm.py）
- G19l 歯ごとの処置: 下書きの「やったこと」から候補（app/ai/toothtx.py。歯が1本に決まる行×config/tooth_treatments.json の表にある言葉だけ）。下書きの画面の「歯ごとの処置」で人が選んだものだけ、確定の取引で歯の状態（tooth_status。前の状態は tooth_status_history）と治療歴へ。番号の札あり。表は9処置
- あとで直す: /fix/{録音}（音声・文字・再整理）。次の患者様の前で止める（actions/rec.js）。/today の印「大川内先生 追記必要」（押すと下書き）
- G26: /sent（app/routers/sent.py）。Claude へ送った文（質問・下書き・聞き違いの直し）を新しい順に出し、伏字は色付き。出す前にもう一度伏字にするので元の名前は出ない
- G26b: 点検係4つ（.claude/agents）、/review-all（docs/総点検.md）、コミット前の見張り .claude/hooks/commit_guard.py
- G26d: 記録・あとで直すのあとは録音を始めた画面へ戻る（全画面と並べた写真も）。場所は actions/rec.js の CVReturn.here、開き直しは view.js。「戻して」は全画面を閉じる動きのまま
- G19b: 録音を止めたら文字起こしまで（区切り＝状態「文字起こし済み」。auto_summary は config/model.json、既定 false）。話した内容の整理の全画面に区切りを順に並べ、「この区切りを要約」「今日の分をまとめて要約」（recpipe.combine、memo.make_combined：直す段を通して、同じ話は1つ・言い直しは後）「この区切りを消す」（5秒だけ元に戻せる）。API は app/routers/segments.py、画面は render.py の _seg_rows と static/js/segments.js。まとめた下書きは drafts.combined=1（区切りが同じ下書きにつながる）。根幹重点などは spellings の決まりで必ず直る
- G19c: 区切りは日付 × 役割で分けて並べる（segview.groups、見出しは render の _seg_rows）。recordings.role は録音を始めた画面の役割（rec.js が渡す）、空なら診療回の担当→歯科医師。「今日の分をまとめて要約」は今日（パソコンの日付）・今の役割の区切りだけ。確定した区切りには消すボタンを出さない。見本データに前の日の確定済み区切りあり（花子様の歯科医師の診療回）
- G19d〜G19i は G19k で清書に置き換わった（readings の置き換え・読みを比べる処理は無い）。terms は40〜80語（ヒント）、glossary は清書へ渡す一覧。scripts/redo_recording.py 録音番号 で録音を清書からやり直す。G19h/i: 整理の指示は「所見はやったこと、指示は説明したこと」。動画用の状態 demo_states の 聞き違い直し_1104c（1104b は残す）
- G19e: 要約・下書きの見出しは「2026年11月6日にやったこと」（memo.title_of。「今日」と書かない）。アレルギー・薬・前回・次回は、記録が空でも quick_answers.json の empty の言葉を出す（ほかの記録にその言葉があれば Claude へ）。見本は3人目に「アレルギー: 特になし」、K は空。聞き違いに 全身起用・今前病変・陰霊 を足した（terms 66語）
- G19f: 区切りの日付と「今日」は診療回の日付（visits.visit_date）。一覧は、この診療回＋同じ患者様の前の診療回の区切り。まとめて要約はこの診療回の・今の役割の分だけ（前の版の古い要約は押し直すと入れ替わる）。見本の前の区切りは花子様の10/23・10/9の診療回。「前回」は診療日の順
- 試験: 全体（偽物の口）。送信文・伏字・応答・モデルを変えたら real_api_check.py の --questions、--memo、--fix、--combine を動かし直す

## 残り
- 録音は /app から開いたときだけ使える。実機のマイクでの通しは院長の確認待ち（試験は偽物のマイク）。初期の文を渡したとき数字が落ちないかの本物の確認は @pytest.mark.gpu（tests/test_fixtalk.py。声の窓が動かす）
- 録音1・2の文字は、院長の聞き違いの例から作り直した架空の文（実際の文字は手元に無い）。本物の録音の文字で確かめたい
- 治療歴は同じ日の診療メモがあると質問の記録に番号を付けない。電話・住所の列は DB に無い
## 次のゴール: 指示待ち
