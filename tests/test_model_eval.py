"""G26c: モデルの比べ方（scripts/model_eval.py）の試験。本物の Claude は呼ばない。"""
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ev():
    spec = importlib.util.spec_from_file_location("model_eval", ROOT / "scripts" / "model_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def r(model, correct, median, **kw):
    return {"model": model, "family": model, "n": 30, "correct": correct, "median": median, "max": median * 2,
            "none_correct": 5, "none_total": 5, "cost_per_q": 0.001, "cost": 0.03, **kw}


def test_thirty_questions_five_without_answer_all_valid(ev, tmp_path, monkeypatch):
    monkeypatch.setenv("CV_DATA_DIR", str(tmp_path))
    import subprocess
    import sys

    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], check=True, capture_output=True,
                   env={**__import__("os").environ, "CV_DATA_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"})
    from app.db import connect

    con = connect()
    assert len(ev.Q) == 30 and sum(1 for q in ev.Q if q[2] is None) == 5
    assert len({q[1] for q in ev.Q}) == 30  # 同じ問いが無い
    assert ev.check_questions(con) == []  # 質問に分けられ、言葉の表に当たらず、正しい記録がある
    con.close()


def test_decision_picks_fastest_within_two_of_best(ev):
    a, b, c = r("a", 30, 3.0), r("b", 28, 1.0), r("c", 27, 0.5)
    assert ev.decide([a, b, c]) is b          # c は3問差で外れ、b が一番速い
    assert ev.decide([a, r("d", 29, 2.0)])["model"] == "d"
    assert ev.decide([r("x", 20, 1.0), r("y", 25, 2.0)])["model"] == "y"  # 正解が大きく違えば速さで選ばない


def test_family_and_cost_use_config_prices(ev):
    assert ev.family_of("claude-haiku-9-9") == "haiku" and ev.family_of("claude-opus-1") == "opus"
    assert ev.family_of("something") == ""
    p = json.loads((ROOT / "config" / "model_prices.json").read_text(encoding="utf-8"))["usd_per_million_tokens"]
    assert set(p) == {"haiku", "sonnet", "opus"}
    assert ev.cost_usd("x-sonnet-y", 1_000_000, 1_000_000) == pytest.approx(p["sonnet"]["input"] + p["sonnet"]["output"])


def test_budget_is_two_dollars_with_margin(ev):
    assert ev.BUDGET_USD == 2.0 and ev.STOP_AT_USD < ev.BUDGET_USD


def test_no_model_name_in_script_and_result_doc_has_three_models():
    assert not re.search(r"claude-(sonnet|opus|haiku|fable)-\d", (ROOT / "scripts" / "model_eval.py").read_text(encoding="utf-8"))
    doc = (ROOT / "docs" / "モデルの選び方.md").read_text(encoding="utf-8")
    for fam in ("haiku", "sonnet", "opus"):
        assert re.search(rf"\| {fam} \| claude-{fam}-", doc)
    assert "採用" in doc and "中央値" in doc


def test_adopted_model_is_what_config_uses():
    doc = (ROOT / "docs" / "モデルの選び方.md").read_text(encoding="utf-8")
    adopted = re.search(r"採用: \*\*(\S+?)\*\*", doc).group(1)
    cfg = json.loads((ROOT / "config" / "model.json").read_text(encoding="utf-8"))
    assert cfg["purposes"]["question"] == adopted
