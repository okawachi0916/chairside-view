# 進捗 voice
- 動く版: G13 完了。/unit で、ボタン2の受付→文字起こし→手元の照合→全画面などの操作。質問・無関係・聞き取り失敗は動かさず一言出す。
- 照合: config/commands.json（42行）と app/voice/interpret.py。試験は偽マイクと /unit?typed=1&hide=1 の cvTyped。
- G08: /voice-test、large-v3（2回目以降 約0.4秒）。設定は config/keys.json、config/voice.json。
- ボタン2の1回止めは CVActive[2]（view.js の isActive から呼ぶ）。
- 残り: G14（口腔内写真の番号の言葉。commands.json の {n} 欄は照合側に対応済み）。HTTPS の用意は院長側。
- 次のゴール: G14
