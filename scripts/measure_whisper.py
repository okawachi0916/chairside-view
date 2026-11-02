"""large-v3 と turbo の文字起こし秒数を測る（2回目以降の秒数）。使い方: python scripts/measure_whisper.py"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.voice import transcribe as tr  # noqa: E402

PHRASE = "重要事項を全画面にして"


def make_wav(path):
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ja-JP' } | Select-Object -First 1;"
        "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
        f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{PHRASE}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


with tempfile.TemporaryDirectory() as d:
    wav = Path(d) / "p.wav"
    make_wav(wav)
    audio = tr.to_pcm(wav.read_bytes())
for name in ("large-v3", "turbo"):
    try:
        tr.transcribe(audio, name)  # 1回目は読み込みを含むので捨てる
        rs = [tr.transcribe(audio, name) for _ in range(3)]
        print(name, [r["seconds"] for r in rs], rs[0]["text"])
    except Exception as e:
        print(name, "失敗", type(e).__name__, str(e)[:120])
