# 進捗 look
- G07e 完了: 全画面と答えの画面にスクロールを出さない。収め方は app/static/js/actions/look.js（2列 fit-2col → 字を小さく --fit → ページ送り）、形は unit.css。答えの枠は幅いっぱい（ai.js は触らず unit.css で上書き）。下書きの画面と /sent も1画面に（rec.css、sent.css）。試験は tests/test_no_scroll.py、画像は docs/画面/G07e。開始時のコミット: c4f3b3e。
- G12-r2 完了: 全画面の見た目の直し。全画面では上の行だけ残し、帯（重要事項も）と本体を隠す（AI の答えだけは重要事項の帯を残す）。題の札と「もとに戻す」などのボタンは枠線に載せる。重要事項は1件ずつ題（赤の太字）と中身を2行に分けた。写真は左の幅を出す枚数で決め、残りの幅は全部一覧に使う。CSS は unit.css と photos.css。画像は C:\hackathon\shots\fullscreen。
- G23 完了: 歯の状態の絵（app/mockview/tooth_chart.py、SVG）。データは tooth_status（app/views/data.py に読み込みを1つ足した）。自院・他院は治療歴の1本の歯と、義歯・ブリッジの作成元から決める。今日の処置の歯は予約の detail から。試験は tests/test_tooth_chart.py。
- G23 の決まりで歯髄の赤と失活のオレンジ（色14番目）を使う。G07d の「赤は BOP・重要事項・録音中だけ」とは、院長の G23 の指示を優先した。
- G07d 完了（見た目の仕上げ）。色・文字・行間・字間・角丸・余白は app/static/css/mock.css の :root に集めた。書体は Noto Sans JP（app/static/fonts に同梱）。
- 決まり: 色13（グレー6、役割3、赤2、琥珀2）、大きさ7段階（14〜56px）、太さ 400/500/700、行間 1.25/1.4/1.7、角丸 8/12px、影なし。試験は tests/test_design_tokens.py。
- 部品は app/mockview/（歯周は perio_parts.py、受付は reception_parts.py）。
- 開始時のコミット: 9dc3e98（main を取り込み済み）
- 前と後の画像: C:\hackathon\shots\G07d\前、後
- 残り: 声の部品の色は actions/voice.js の中に書かれている（JS は変えない約束）。mock.css から変数で上書きした。/voice-test の画面は対象外。
- 次のゴール: 指示待ち

## 院長が見るアドレス（8840 の場所）
- http://localhost:8840/ 予約一覧
- http://localhost:8840/unit ユニットの画面、http://localhost:8840/reception 受付の画面
- http://localhost:8840/mock/ 見本の予約一覧（/mock/doctor、/mock/hygienist、/mock/reception）
