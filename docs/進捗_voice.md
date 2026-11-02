# 進捗 voice
- 動く版: G14 完了（G13 の上）。/unit で声または文字から「3番を拡大して」「1番と5番を大きく」などで口腔内写真を出せる。
- 写真: 架空の絵12枚（data/photos、photos.json、scripts/make_photos.py）。番号 n は一覧の (n-1) 番目を使い、件数で折り返す。差し替えは画像と file を書き換える。
- 一覧に戻す = 全画面を閉じる（拡大の状態は閉じると消える。隠して戻すと残る）。
- 声の操作: config/commands.json（50行）、app/voice/interpret.py、app/static/js/actions/voice.js。受付の画面では使わない。
- G08: /voice-test、large-v3（2回目以降 約0.4秒）。HTTPS の用意は院長側。
- 残り: なし。
- 次のゴール: 指示待ち
