"""コミット予定のファイルに鍵・パスワード・DB・音声・data/runtime があれば止める。"""
import re
import subprocess
import sys

BAD_EXT = (".db", ".sqlite", ".sqlite3", ".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac")
PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8").stdout


def main():
    files = [f for f in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if f]
    problems = []
    for f in files:
        low = f.lower().replace("\\", "/")
        if low.startswith("data/runtime/") or "/data/runtime/" in low:
            problems.append(f"{f}: data/runtime の中身")
        elif low.endswith(BAD_EXT):
            problems.append(f"{f}: データベースか音声ファイル")
        if low.endswith(".env") or low.rsplit("/", 1)[-1].startswith(".env"):
            problems.append(f"{f}: 環境ファイル")
        if low.endswith("check_secrets.py"):
            continue
        text = git("show", f":{f}")
        for p in PATTERNS:
            if p.search(text):
                problems.append(f"{f}: 鍵やパスワードらしい文字")
                break
    if problems:
        print("止めました:")
        for p in problems:
            print(" -", p)
        return 1
    print("check_secrets: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
