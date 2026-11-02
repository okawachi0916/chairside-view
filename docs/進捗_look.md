# 進捗 look
- 動く版: G07d 完了（見た目の仕上げ）。色・文字・行間・字間・角丸・余白は app/static/css/mock.css の :root に集めた。書体は Noto Sans JP（app/static/fonts に同梱）。
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
