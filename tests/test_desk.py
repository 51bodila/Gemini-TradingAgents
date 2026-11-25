"""Offline: fake tools and a fake model. Checks the pipeline order (Neon brain -> Hydrogen backtest + Argon committee
-> Carbon judge -> Python rules -> order) and that a failing stage never stops the run."""
import json
from gemini_desk import brain, data, desk, judge as judge_mod, stages
from gemini_desk.llm import Usage
import tempfile


def _tmp():
    return tempfile.mkdtemp(prefix="gd-test-")

PLAN = {"direction": "long", "horizon": "4 weeks", "thesis": "trend intact", "invalidation": "close below SMA50",
        "strategies": [{"name": "sma_20_50", "rules": "long when SMA20 > SMA50"}], "key_risks": ["earnings"]}


class FakeLLM:
    def __init__(self, verdict, brain_ok=True):
        self.usage, self.verdict, self.brain_ok, self.calls = Usage(), verdict, brain_ok, []

    def ask(self, role, model, system, prompt, json_mode=False, schema=None):
        self.calls.append((role, model, prompt))
        if role == "brain":
            if not self.brain_ok:
                raise RuntimeError("Model gemini-4-neon needs billing")
            return json.dumps(PLAN)
        return json.dumps(self.verdict)


def _patch(mp, seen):
    bars = [(f"2026-01-{(i % 28) + 1:02d}", 90 + i * .1, 91 + i * .1, 89 + i * .1, 90 + i * .1, 1000.0) for i in range(300)]
    mp.setattr(data, "daily_bars", lambda s, days=400: bars)

    def vibe(sym, dry_run=False, deep=False, plan="", iters=None):
        seen["vibe_plan"] = plan
        return {"stage": "vibe_trading", "status": "ok", "model": "m", "command": "c", "output": "vibe_trading says hi", "stderr": ""}
    mp.setattr(stages, "vibe_trading", vibe)
    mp.setattr(stages, "committee", lambda sym, dry_run=False: {"stage": "committee", "status": "ok", "model": "m", "command": "c", "output": "committee says hi", "stderr": ""})
    mp.setattr(stages, "trading_agents_raw", lambda q, dry_run=False: {"stage": "TradingAgents", "status": "not available", "model": "m", "command": "", "output": "", "stderr": "no wsl"})
    mp.setattr(stages, "has_aihf_data", lambda: False)
    mp.setattr(judge_mod, "judge", lambda llm, sym, mt, st, mand, dry_run=False: (judge_mod.parse_json(llm.ask("judge", "gemini-4-carbon", "", judge_mod._prompt(sym, mt, st, mand))), "fake"))
    mp.setattr(desk, "judge", judge_mod.judge)


def test_go_smaller(monkeypatch, tmp_path=None):
    seen = {}
    _patch(monkeypatch, seen)
    llm = FakeLLM({"verdict": "GO", "decision": "long", "entry": 119.9, "stop": 114.9, "target": 132.4, "reasons": ["r"]})
    r = desk.run(llm, "TEST", str(_tmp()), capital=10_000)
    assert [c[0] for c in llm.calls] == ["brain", "judge"]                 # Neon first, Carbon last
    assert "sma_20_50" in seen["vibe_plan"] and "trend intact" in seen["vibe_plan"]   # Hydrogen backtests Neon's plan
    assert abs(r["calc"]["reward_risk"] - 2.5) < 1e-9
    assert r["rules"]["verdict"] == "GO SMALLER" and abs(r["calc"]["position_pct_capital"] - 20) < 1e-6  # 24% cut to 20% cap
    assert r["final"] == "GO SMALLER" and r["order"]["side"] == "buy"
    judge_prompt = llm.calls[1][2]
    assert "committee says hi" in judge_prompt and "vibe_trading says hi" in judge_prompt and "HARD RULES" in judge_prompt
    md = desk.report_md(r, llm.usage.table())
    assert md.index("Neon's thesis") < md.index("What each system said")


def test_neon_fails_default_plan(monkeypatch):
    seen = {}
    _patch(monkeypatch, seen)
    llm = FakeLLM({"verdict": "NO-GO", "decision": "no trade", "reasons": ["r"]}, brain_ok=False)
    r = desk.run(llm, "TEST", str(_tmp()), capital=10_000)
    assert r["stages"][0]["status"].startswith("failed") and "billing" in r["stages"][0]["stderr"]
    assert "default (Neon unavailable)" in seen["vibe_plan"]              # Hydrogen still runs, on the default plan
    assert r["final"] == "NO-GO" and r["judge_engine"] == "fake"           # judge still ran


def test_rules_override_model(monkeypatch):
    _patch(monkeypatch, {})
    llm = FakeLLM({"verdict": "GO", "decision": "long", "entry": 119.9, "stop": 119.5, "target": 130, "reasons": ["r"]})
    r = desk.run(llm, "TEST", str(_tmp()), capital=10_000)
    assert r["final"] == "NO-GO" and r["order"] is None   # stop 0.4 away < 0.5 ATR: rules win over the model's GO


def test_fast_mode_one_argon_call(monkeypatch):
    seen = {}
    _patch(monkeypatch, seen)
    called = {"swarm": False}
    monkeypatch.setattr(stages, "committee", lambda sym, dry_run=False: called.__setitem__("swarm", True) or {})
    llm = FakeLLM({"verdict": "NO-GO", "decision": "no trade", "reasons": ["r"]})
    r = desk.run(llm, "TEST", str(_tmp()), capital=10_000, fast=True)
    assert not called["swarm"]                                              # no 4-agent swarm in --fast
    assert [c[0] for c in llm.calls] == ["brain", "committee (one call)", "judge"]
    assert "vibe_trading says hi" in llm.calls[1][2] and "trend intact" in llm.calls[1][2]   # debate sees pack + plan
