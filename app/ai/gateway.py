"""Claude へ送る処理はここだけ。ほかの場所から直接 Claude を呼ばない。

送る前に伏字にし、残りがあれば送らずに止め、送った文を data/runtime/sent_log に残す。
対応表は send() の中だけで作る。同時に呼んでも混ざらない。
"""
import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.ai.redact import RedactionFailed, Sensitive, Table, check_clean
from app.ai.settings import ClaudeUnavailable, load_key, load_model, redact_key
from app.db import data_dir

_log_lock = threading.Lock()


@dataclass
class Reply:
    text: str         # 元の名前に戻した応答
    masked_text: str  # Claude が返した、伏字のままの応答


class AnthropicMouth:
    """本物の Claude の口。鍵とモデル名は使うときに読む。"""

    def complete(self, system: str, user: str, max_tokens: int) -> str:
        import anthropic  # この中だけで読み込む

        client = anthropic.Anthropic(api_key=load_key())  # ANTHROPIC_API_KEY は使わない
        kwargs = {"system": system} if system else {}
        res = client.messages.create(
            model=load_model(), max_tokens=max_tokens, messages=[{"role": "user", "content": user}], **kwargs
        )
        return "".join(b.text for b in res.content if getattr(b, "type", "") == "text")


class Gateway:
    def __init__(self, mouth=None, log_dir=None, masker=Table):
        self.mouth = mouth or AnthropicMouth()
        self._log_dir = Path(log_dir) if log_dir else None
        self._masker = masker  # 試験で、わざと壊した伏字を差し込むための入口

    @property
    def log_dir(self) -> Path:
        return self._log_dir or data_dir() / "sent_log"

    def send(self, user: str, sensitive: Sensitive, *, system: str = "", max_tokens: int = 1024,
             purpose: str = "") -> Reply:
        table = self._masker(sensitive)
        m_user = table.mask(user)
        m_system = table.mask(system)
        check_clean(table, m_user + "\n" + m_system)  # 残っていれば RedactionFailed。送らない
        self._log(purpose, m_system, m_user)
        try:
            raw = self.mouth.complete(m_system, m_user, max_tokens)
        except ClaudeUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(redact_key(f"Claude への送信に失敗しました（{type(e).__name__}）")) from None
        return Reply(text=table.restore(raw), masked_text=raw)

    def _log(self, purpose, m_system, m_user):
        d = self.log_dir
        d.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        line = json.dumps(
            {"time": now.isoformat(timespec="seconds"), "purpose": purpose, "system": m_system, "user": m_user},
            ensure_ascii=False,
        )
        with _log_lock, (d / f"{now:%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def sensitive_from_db(con, clinics=None) -> Sensitive:
    """データベースの患者様とスタッフから、伏字にする一覧を作る。"""
    from app.ai.redact import Patient

    patients = [
        Patient(name=r["name"], kana=r["name_kana"], chart_no=r["chart_no"], birth_date=r["birth_date"])
        for r in con.execute("SELECT name, name_kana, chart_no, birth_date FROM patients")
    ]
    staff = set()
    for table in ("appointments", "treatment_plans"):
        try:
            staff |= {r[0] for r in con.execute(f"SELECT DISTINCT staff_name FROM {table} WHERE staff_name != ''")}
        except Exception:  # noqa: BLE001  表の無い版でも動く
            pass
    return Sensitive(patients=patients, staff=sorted(staff), clinics=list(clinics or []))
