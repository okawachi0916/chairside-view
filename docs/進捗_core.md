# 進捗 core
- 動く版: G11 完了（G10 の上）。ユニットの画面にボタン3（隠す・戻す・次の患者様へ）。
  - 操作の入口は app/static/js/actions.js の CVActions.run(名前)。ボタンn は "button"+n、画面のボタンも通す。
    ほかの窓は register で足す（actions/担当.js）。ボタン3は "hide-toggle"、次へ進むのは "pick-patient"。
  - 隠すと画面の部品を DOM から外して保管（文字は残らない）。戻すと全画面・スクロールもそのまま戻る。
  - 次の患者様を開く（cv.openUnit）と "clear-transient" で保管と一時の情報を消す。診療の記録はサーバー側なので消えない。
  - 2回押しと帯は G08 の voice_keys.js。隠している間の帯の文だけ textFor で差し替え（voice_keys.js に1行足した）。
  - 読み込み中の応答は hide のとき cv.cancel() で捨てる。
- 試験: tests/test_button3.py（9件）。全体 58件通過。
- 残り: 全画面（G12）。ボタン1・2 は voice が register("button1") などで足す。
- 次のゴール: G12
