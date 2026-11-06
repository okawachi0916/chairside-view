"""G14o 実測: Windows の読み上げ（Haruka）で作った声を、作品と同じ音声認識（config/voice.json のモデル）に通し、
実際に出た聞き違いを tests/mishear_measure/results.json に残す。声の指示（ボタン2）と同じく initial_prompt は渡さない。
使い方: python tests/mishear_measure/measure.py   （GPU を使う。音声は一時フォルダに作り、終わったら消す）
声の変え方: 速さ(rate -2,0,2,4)、高さ(SSML pitch)、語尾を短く切る(0.0 / 0.18 秒)。"""
import itertools
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.voice.interpret import example  # noqa: E402
from app.voice.transcribe import transcribe  # noqa: E402

OUT = Path(__file__).with_name("results.json")
NUM_READ = {1: "いち", 2: "に", 3: "さん", 4: "よん", 6: "ろく", 7: "なな", 9: "きゅう", 10: "じゅう", 11: "じゅういち", 12: "じゅうに"}
RATES = [-2, 0, 2, 4]
PITCHES = ["medium", "+25%"]
TRIMS = [0.0, 0.18]


def phrases():
    rows = json.loads((ROOT / "config" / "commands.json").read_text(encoding="utf-8"))
    ws = []
    for r in rows:
        w = r["言葉"]
        if "{" in w or r["状態"] != "使える":
            continue
        e = example(w)
        if e not in ws:
            ws.append(e)
    for n, rd in NUM_READ.items():
        ws += [f"{n}番", f"{rd}ばん", f"{n}番を拡大して", f"{n}番を開いて"]
    return list(dict.fromkeys(ws))


PS = r"""
Add-Type -AssemblyName System.Speech
$jobs = Get-Content -Raw -Encoding UTF8 $args[0] | ConvertFrom-Json
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Haruka Desktop')
foreach ($j in $jobs) {
  $s.Rate = [int]$j.rate
  $s.SetOutputToWaveFile($j.path)
  $ssml = '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ja-JP"><prosody pitch="' + $j.pitch + '">' + $j.text + '</prosody></speak>'
  $s.SpeakSsml($ssml)
}
$s.Dispose()
"""


def synth_all(jobs, ps1, jobfile):
    """全部の声を PowerShell 1回で作る（1つずつ起動すると遅い）。"""
    jobfile.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    ps1.write_text(PS, encoding="utf-8-sig")
    subprocess.run(["powershell", "-NoProfile", "-File", str(ps1), str(jobfile)], check=True, capture_output=True)


def load_wav(path, trim):
    with wave.open(str(path)) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    if sr != 16000:
        a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * 16000 / sr)), np.arange(len(a)), a).astype(np.float32)
    nz = np.flatnonzero(np.abs(a) > 0.01)  # 後ろの無音を落としてから、語尾を切る
    if len(nz):
        a = a[: nz[-1] + 1]
    if trim:
        a = a[: max(1600, len(a) - int(16000 * trim))]
    return np.concatenate([np.zeros(4000, np.float32), a, np.zeros(8000, np.float32)])


def main():
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    rows = res.get("結果", [])
    done = {(r["言った"], r["速さ"], r["高さ"], r["切る秒"]) for r in rows}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        jobs = [{"text": t, "rate": r, "pitch": p, "path": str(td / f"{i}.wav")}
                for i, (t, r, p) in enumerate(itertools.product(phrases(), RATES, PITCHES))]
        synth_all(jobs, td / "tts.ps1", td / "jobs.json")
        for n, j in enumerate(jobs):
            for trim in TRIMS:
                if (j["text"], j["rate"], j["pitch"], trim) in done:
                    continue
                heard = transcribe(load_wav(j["path"], trim))["text"]
                rows.append({"言った": j["text"], "速さ": j["rate"], "高さ": j["pitch"], "切る秒": trim, "聞こえた": heard})
            if n % 40 == 0:
                OUT.write_text(json.dumps({"声": "Microsoft Haruka Desktop (ja-JP)", "結果": rows}, ensure_ascii=False, indent=0), encoding="utf-8")
    OUT.write_text(json.dumps({"声": "Microsoft Haruka Desktop (ja-JP)", "結果": rows}, ensure_ascii=False, indent=0), encoding="utf-8")
    print("done", len(rows))


if __name__ == "__main__":
    main()
