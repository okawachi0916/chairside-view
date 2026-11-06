/* マイクが使えなかったとき、何が起きたかと、次にすることを日本語で返す共通の部品（G14p）。
   録音・声の操作・下書き・状況の画面が同じ言葉を出す。機器の名前や1台のマイクには決め打ちしない（ブラウザが返す失敗の種類で分ける）。
   CVMicError.explain(e) → Promise<文字>   失敗（getUserMedia の例外）の説明
   CVMicError.unsupported() → 文字          navigator.mediaDevices が無いときの説明
   CVMicError.silent(stream) → 文字 or ""   つないだが、ミュート・無効で音が来ない状態の説明 */
(function () {
  var USE_BLOCKED = "ブラウザがこのサイトのマイクを止めています。アドレス欄の左のアイコン →「マイク」→「許可」に変えて、ページを開き直してください";
  var USE_ASK = "マイクの許可が出ていません。確認の表示が出たら「許可」を選んでください（出ないときはアドレス欄の左のアイコン →「マイク」→「許可」）";

  function unsupported() {
    if (window.isSecureContext === false) {
      return "この接続（http の別のパソコンから）ではブラウザがマイクを使わせません。マイクのあるパソコンで http://localhost:ポート番号/ を開いてください";
    }
    return "このブラウザではマイクを使えません。Edge か Chrome の新しい版で開いてください";
  }

  function explain(e) {
    var name = (e && e.name) || "";
    if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
      if (navigator.permissions && navigator.permissions.query) {
        return navigator.permissions.query({ name: "microphone" }).then(function (st) {
          return st.state === "denied" ? USE_BLOCKED : USE_ASK;
        }).catch(function () { return USE_BLOCKED; });
      }
      return Promise.resolve(USE_BLOCKED);
    }
    if (name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError") {
      return Promise.resolve("マイクが見つかりません。USB の差し込みと、Windows の「既定の録音機器」を確かめてください");
    }
    if (name === "NotReadableError" || name === "AbortError" || name === "TrackStartError") {
      return Promise.resolve("マイクを使えません: ほかのアプリがつかんでいるか、機器が応答していません。Zoom・OBS・Discord・Voicemeeter など音を使うアプリを閉じて、もう一度お試しください");
    }
    return Promise.resolve("マイクを使えません（" + (name || (e && e.message) || "原因不明") + "）");
  }

  function silent(stream) {
    var tracks = stream && stream.getAudioTracks ? stream.getAudioTracks() : [];
    if (!tracks.length) return "マイクから音の通り道が来ません。機器を確かめてください";
    if (tracks.every(function (t) { return t.readyState === "ended"; })) return "マイクが外れました。差し込みを確かめてください";
    if (tracks.every(function (t) { return t.enabled === false; })) return "マイクが無効になっています";
    if (tracks.every(function (t) { return t.muted; })) return "マイクがミュートになっています。マイク本体のミュートや、Windows のマイクの音量を確かめてください";
    return "";
  }

  window.CVMicError = { explain: explain, unsupported: unsupported, silent: silent };
})();
