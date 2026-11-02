# 進捗 voice
- 動く版: G08 完了。/voice-test で、キー名表示・2回押しと帯・録音→文字起こしが通る（偽マイクの試験は9件通過）。
- 文字起こし: large-v3 を採用。2回目以降 約0.4秒（turbo は約0.2秒）。初回のモデル読み込みは約8秒なので、起動時に裏で読んでおく。測る道具は scripts/measure_whisper.py。
- 設定: config/keys.json（キー・時間）、config/voice.json（モデル名）。
- 音声は保存しない。ffmpeg は PATH にある物を使う。
- 残り: 本物の院内HTTPS（chairside.shika.life）の用意は院長側。commands.json は未作成。
- 次のゴール: G09 以降（担当は指示ファイルで確認）
