# 進捗 core
- 動く版: G09 完了。データベース app/db（schema・initial・update）、scripts/seed.py、scripts/update_db.py、試験12本。
  - 架空の5人（花子 0123、一郎 0456、太郎 0789、和子 1024、美咲 2048）と今日の予約6行が data/runtime/app.db に入る。
  - 花子は見本の3画面と同じ内容（診療メモ8、治療歴10、写真12、歯周検査2回など）。
  - 診療メモと下書きは (診療回, 患者様) の組で診療回につなぐ。
- G09 は G02 まで取り込んだ main（85e6a1d）から開始。
- 写真の画像はまだ無い（file 列は空）。画像は data/runtime/photos に置く前提。
- 試験: tests/test_db.py（一時フォルダで seed を2回、古いDBへ update_db）。
- 残り: 画面へのつなぎ（G10 以降）。仕様の質問3つは G02 で決定済み。
- 次のゴール: G10
