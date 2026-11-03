"""コミット前の見張り（PreToolUse の Bash フック）。

git commit を含むコマンドのときだけ動く。それ以外はすぐ通す（終了コード 0）。
コミットする物に次があれば、終了コード 2 で止めて理由を日本語で出す。
  - scripts/check_secrets.py が見つけるもの（鍵の形、データベース、環境ファイルなど）
  - 音声ファイル
  - 位置情報（GPS）の入った写真
  - data/runtime の中身
見張り自身が例外で落ちたときは止めずに通し、警告だけ出す。見張りの不具合でコミットが止まらないようにする。
"""
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

AUDIO_EXT = (".wav", ".mp3", ".m4a", ".aac", ".webm", ".ogg", ".oga", ".opus", ".flac", ".wma", ".amr", ".aiff")
PHOTO_EXT = (".jpg", ".jpeg", ".jpe", ".tif", ".tiff", ".png", ".webp", ".heic", ".heif")
GPS_TAG = 0x8825

# git commit（git -C パス commit、git -c 設定 commit も）。git commit-tree などは含めない
COMMIT = re.compile(r"(?:^|[\s;&|(])git(?:\s+(?:-C\s+(?:\"[^\"]+\"|'[^']+'|\S+)|-c\s+\S+|--no-pager|--git-dir=\S+|--work-tree=\S+))*\s+commit(?![\w-])")
GIT_C = re.compile(r"git\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+)")
STAGES_MORE = re.compile(r"(?:^|[\s;&|(])git(?:\s+-C\s+\S+)?\s+add\b|\bcommit\b[^;&|]*\s(?:-[a-zA-Z]*a[a-zA-Z]*|--all)\b")


def is_commit(command: str) -> bool:
    return bool(COMMIT.search(command or ""))


def repo_dir(command: str, cwd: str) -> str:
    m = GIT_C.search(command or "")
    if m:
        p = m.group(1).strip("\"'")
        return p if os.path.isabs(p) else os.path.join(cwd or ".", p)
    return cwd or "."


def git(repo: str, *args: str, binary: bool = False):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def target_files(repo: str, command: str) -> list:
    """コミットに入る物。add と同じコマンドや commit -a のときは、作業中の変更も入れて調べる。"""
    files = {f for f in git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0") if f}
    if STAGES_MORE.search(command or ""):
        for line in git(repo, "status", "--porcelain", "-z", "--untracked-files=all").split("\0"):
            if len(line) > 3 and line[:2].strip() and "D" not in line[:2]:
                files.add(line[3:])
    return sorted(files)


def read_bytes(repo: str, path: str) -> bytes:
    staged = git(repo, "show", f":{path}", binary=True)
    if staged:
        return staged
    try:
        return (Path(repo) / path).read_bytes()
    except OSError:
        return b""


def _ifd_has_gps(tiff: bytes) -> bool:
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return False
    e = "<" if tiff[:2] == b"II" else ">"
    off = struct.unpack(e + "I", tiff[4:8])[0]
    seen = set()
    while 0 < off + 2 <= len(tiff) and off not in seen:
        seen.add(off)
        n = struct.unpack(e + "H", tiff[off:off + 2])[0]
        for i in range(n):
            p = off + 2 + i * 12
            if p + 12 > len(tiff):
                return False
            if struct.unpack(e + "H", tiff[p:p + 2])[0] == GPS_TAG:
                return True
        nxt = off + 2 + n * 12
        if nxt + 4 > len(tiff):
            return False
        off = struct.unpack(e + "I", tiff[nxt:nxt + 4])[0]
    return False


def has_gps(data: bytes) -> bool:
    """JPEG の Exif、PNG の eXIf、TIFF に GPS の項目があるか。"""
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 4 <= len(data) and data[i] == 0xFF:
            marker = data[i + 1]
            if marker in (0xD9, 0xDA):
                break
            size = struct.unpack(">H", data[i + 2:i + 4])[0]
            seg = data[i + 4:i + 2 + size]
            if marker == 0xE1 and seg[:6] == b"Exif\0\0" and _ifd_has_gps(seg[6:]):
                return True
            i += 2 + size
        return False
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        i = 8
        while i + 8 <= len(data):
            size = struct.unpack(">I", data[i:i + 4])[0]
            if data[i + 4:i + 8] == b"eXIf" and _ifd_has_gps(data[i + 8:i + 8 + size]):
                return True
            i += 12 + size
        return False
    if data[:2] in (b"II", b"MM"):
        return _ifd_has_gps(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        k = data.find(b"EXIF")
        return k > 0 and _ifd_has_gps(data[k + 8:].removeprefix(b"Exif\0\0"))
    return False


def run_checks(repo: str, command: str) -> list:
    problems = []
    script = Path(repo) / "scripts" / "check_secrets.py"
    if script.exists():
        r = subprocess.run([sys.executable, str(script)], cwd=repo, capture_output=True,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if r.returncode != 0:
            out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
            problems.append("scripts/check_secrets.py が止めました:\n" + out)
    for f in target_files(repo, command):
        low = f.lower().replace("\\", "/")
        if low.startswith("data/runtime/") or "/data/runtime/" in low:
            problems.append(f"{f}: data/runtime の中身はコミットしません")
        if low.endswith(AUDIO_EXT):
            problems.append(f"{f}: 音声ファイルはコミットしません")
        if low.endswith(PHOTO_EXT) and has_gps(read_bytes(repo, f)):
            problems.append(f"{f}: 写真に位置情報（GPS）が入っています。消してからコミットしてください")
    return problems


def main(stdin=None) -> int:
    try:
        event = json.loads((stdin or sys.stdin).read() or "{}")
        command = (event.get("tool_input") or {}).get("command", "")
        if not is_commit(command):
            return 0
        problems = run_checks(repo_dir(command, event.get("cwd") or os.getcwd()), command)
    except Exception as e:  # noqa: BLE001  見張りの不具合でコミットを止めない
        print(f"警告: コミットの見張りが動かず、確かめずに通しました（{type(e).__name__}）", file=sys.stderr)
        return 0
    if problems:
        print("コミットを止めました:\n- " + "\n- ".join(problems), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
