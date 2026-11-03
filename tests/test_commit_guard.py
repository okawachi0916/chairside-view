"""G26b: コミット前の見張り（.claude/hooks/commit_guard.py）の試験。本物のリポジトリは触らず、一時のリポジトリで動かす。"""
import importlib.util
import io
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "commit_guard.py"
FAKE_KEY = "sk-" + "ant-" + "a1B2c3D4e5F6g7H8i9J0"  # 試験用の偽の鍵（本物ではない）


def load_guard():
    spec = importlib.util.spec_from_file_location("commit_guard", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def jpeg(with_gps: bool) -> bytes:
    tag = 0x8825 if with_gps else 0x0112
    ifd = struct.pack("<H", 1) + struct.pack("<HHII", tag, 4, 1, 0) + struct.pack("<I", 0)
    tiff = b"II*\x00" + struct.pack("<I", 8) + ifd
    seg = b"Exif\0\0" + tiff
    return b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", len(seg) + 2) + seg + b"\xff\xd9"


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "check_secrets.py", r / "scripts" / "check_secrets.py")
    for a in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True)
    return r


def stage(repo, name, data):
    p = repo / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    subprocess.run(["git", "-C", str(repo), "add", "-f", name], check=True, capture_output=True)


def run_hook(repo, command):
    event = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo)})
    return subprocess.run([sys.executable, str(HOOK)], input=event, capture_output=True, text=True, encoding="utf-8")


COMMIT = 'git commit -m "試し"'


def test_plain_commit_passes(repo):
    stage(repo, "app/a.py", "print('こんにちは')\n")
    stage(repo, "photos/ok.jpg", jpeg(False))
    r = run_hook(repo, COMMIT)
    assert r.returncode == 0, r.stderr


def test_secret_key_blocks(repo):
    stage(repo, "app/conf.py", f'KEY = "{FAKE_KEY}"\n')
    r = run_hook(repo, COMMIT)
    assert r.returncode == 2 and "コミットを止めました" in r.stderr and "check_secrets" in r.stderr
    assert FAKE_KEY not in r.stderr  # 鍵そのものは出さない


@pytest.mark.parametrize("name", ["rec/a.wav", "x/voice.mp3", "audio/rec_1.webm", "m.m4a", "z.flac"])
def test_audio_blocks(repo, name):
    stage(repo, name, b"RIFF....")
    r = run_hook(repo, COMMIT)
    assert r.returncode == 2 and "音声" in r.stderr and name in r.stderr


def test_photo_with_gps_blocks_and_without_passes(repo):
    stage(repo, "photos/gps.jpg", jpeg(True))
    r = run_hook(repo, COMMIT)
    assert r.returncode == 2 and "位置情報" in r.stderr and "gps.jpg" in r.stderr
    subprocess.run(["git", "-C", str(repo), "rm", "-q", "--cached", "photos/gps.jpg"], check=True, capture_output=True)
    stage(repo, "photos/clean.jpg", jpeg(False))
    assert run_hook(repo, COMMIT).returncode == 0


def test_data_runtime_blocks(repo):
    stage(repo, "data/runtime/notes.txt", "メモ")
    r = run_hook(repo, COMMIT)
    assert r.returncode == 2 and "data/runtime" in r.stderr


def test_add_and_commit_in_one_command_is_checked(repo):
    (repo / "rec.wav").write_bytes(b"RIFF....")  # まだ add していない
    r = run_hook(repo, 'git add -A && git commit -m "まとめて"')
    assert r.returncode == 2 and "rec.wav" in r.stderr


def test_commit_with_dash_C_path_is_checked(repo, tmp_path):
    stage(repo, "a.wav", b"RIFF")
    event = json.dumps({"tool_input": {"command": f'git -C "{repo}" commit -m x'}, "cwd": str(tmp_path)})
    r = subprocess.run([sys.executable, str(HOOK)], input=event, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2


@pytest.mark.parametrize("command", [
    "git status", "git add -A", "git log --oneline", "git push origin main", "git commit-tree abc",
    "echo git commit", "ls -la", "python -m pytest -q", "git diff --cached", "",
])
def test_other_commands_pass_even_with_bad_files(repo, command):
    stage(repo, "bad.wav", b"RIFF")
    stage(repo, "k.py", f'KEY = "{FAKE_KEY}"\n')
    r = run_hook(repo, command)
    if command == "echo git commit":
        assert r.returncode in (0, 2)  # 文の中に出てくるだけの git commit は区別しない（安全側で止めてよい）
    else:
        assert r.returncode == 0 and r.stderr == ""


def test_other_tools_and_broken_input_pass(repo):
    stage(repo, "bad.wav", b"RIFF")
    for text in ["", "{}", "これはJSONではない", '{"tool_input": null}', '{"tool_input": {"command": 5}}']:
        r = subprocess.run([sys.executable, str(HOOK)], input=text, capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, text


def test_guard_crash_lets_commit_through_with_warning(repo, monkeypatch, capsys):
    guard = load_guard()

    def boom(*a, **k):
        raise RuntimeError("見張りの不具合")

    monkeypatch.setattr(guard, "run_checks", boom)
    event = json.dumps({"tool_input": {"command": COMMIT}, "cwd": str(repo)})
    assert guard.main(io.StringIO(event)) == 0
    assert "警告" in capsys.readouterr().err


def test_guard_crash_when_repo_is_missing_passes(tmp_path):
    event = json.dumps({"tool_input": {"command": COMMIT}, "cwd": str(tmp_path / "ない")})
    r = subprocess.run([sys.executable, str(HOOK)], input=event, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0


def test_settings_json_registers_the_guard():
    cfg = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hooks = cfg["hooks"]["PreToolUse"]
    assert hooks[0]["matcher"] == "Bash"
    assert "commit_guard.py" in hooks[0]["hooks"][0]["command"]


def test_agents_are_read_only_with_models():
    expect = {"medical-wording": "sonnet", "public-safety": "haiku", "judge-view": "sonnet", "test-gap": "sonnet"}
    for name, model in expect.items():
        text = (ROOT / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
        head = text.split("---")[1]
        assert f"name: {name}" in head and f"model: {model}" in head
        tools = [l for l in head.splitlines() if l.startswith("tools:")][0]
        assert {t.strip() for t in tools.split(":", 1)[1].split(",")} == {"Read", "Grep", "Glob"}
    assert (ROOT / ".claude" / "skills" / "review-all" / "SKILL.md").exists()
