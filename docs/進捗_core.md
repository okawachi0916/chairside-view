# 進捗 core
- 動く版: G12 完了（G11 の上）。重要事項・口腔内写真・話した内容の整理の全画面。ほかの全画面ボタンは何も起きない。
  - 全画面の操作は actions.js の入口を通る: fs-open（部品名）、fs-close、fs-next、fs-prev、fs-photo。
  - 中身は画面の <template data-fs="部品名"> に入れてあり、開くまでページの文字に出ない（render.py の fullscreen_templates）。
  - 上の行と重要事項の帯は残り、body に fs-mode が付いて本体を隠す。1画面に入らないときだけ「前のページ」「次のページ」が出る。
  - ボタン3で隠して戻すと全画面まで戻る。次の患者様を開くと全画面は消える。
- データ: important_notes に period・detail、drafts に transcript を追加。花子の今日の診療回2件と下書き2件を初期データに足した。
  update_db.py で古いDBにも足せる。app/views/data.py の con() が初回に自動で足りない分を足す。
- 試験: tests/test_fullscreen.py（7件）。全体 65件通過。
- 残り: 録音と声の窓（ボタン1・2）は register("button1") などで足す。
- 次のゴール: 指示待ち
