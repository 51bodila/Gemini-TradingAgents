"""Neon runs first: the brain. From the ticker and a free price snapshot it writes the thesis and the test plan
that Hydrogen backtests and Argon's committee debates. TradingAgents does the research when it is installed;
otherwise the same question goes straight to Gemini 4 Neon. If Neon fails, a default plan keeps the run going.
"""
import json
import re

from . import stages
from .llm import parse_json
from .roles import model_for

PLAN_SCHEMA = {"type": "OBJECT", "properties": {
    "direction": {"type": "STRING", "enum": ["long", "short", "neutral"]},
    "horizon": {"type": "STRING"},
    "thesis": {"type": "STRING"},
    "strategies": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"name": {"type": "STRING"}, "rules": {"type": "STRING"}}}},
    "key_risks": {"type": "ARRAY", "items": {"type": "STRING"}},
    "invalidation": {"type": "STRING"}},
    "required": ["direction", "thesis", "strategies", "invalidation"]}

DEFAULT_PLAN = {"direction": "neutral", "horizon": "2-6 weeks", "source": "default (Neon unavailable)",
                "thesis": "No thesis from Neon; test plain trend-following against buy-and-hold.",
                "strategies": [{"name": "buy_and_hold", "rules": "buy at the start, hold to the end"},
                               {"name": "sma_20_50", "rules": "long when SMA20 > SMA50, flat otherwise"}],
                "key_risks": [], "invalidation": "n/a"}

ASK = """You are the lead analyst (the brain) of a trading desk. Asset: {sym}.
Free price snapshot computed by Python from Yahoo Finance:
{snapshot}

Write the desk's working thesis for the next 2-6 weeks and a TEST PLAN that a backtester will run on daily data.
First say WHY you would trade at all and what the edge is, in at most five sentences, and who would be on the
other side of the trade. Then pick 2-3 simple, mechanical strategies that would prove or disprove the thesis (exact rules: indicators, periods,
entry, exit). Name the key risks and what would prove the thesis wrong. Use only the numbers above or your own tool
results; do not invent prices.
Backtests must include fees, at least 30 trades, and a walk-forward window; signals may only use data available
before the bar they trade.
End your answer with one JSON object with keys: direction (long|short|neutral), horizon, thesis, edge, other_side,
strategies (list of {{name, rules}}), key_risks (list), invalidation."""


def _json_tail(text):
    m = re.findall(r"\{.*\}", text or "", flags=re.S)
    for cand in reversed(m):
        try:
            j = json.loads(cand)
            if isinstance(j, dict) and "strategies" in j:
                return j
        except json.JSONDecodeError:
            continue
    return None


def think(llm, sym, snapshot, dry_run=False):
    """Returns (plan dict, stage dict for the report)."""
    q = ASK.format(sym=sym, snapshot=snapshot)
    ta = stages.trading_agents_raw(q, dry_run)
    plan = _json_tail(ta.get("output", "")) if ta["status"] == "ok" else None
    if plan:
        plan["source"] = "TradingAgents on " + model_for("strategist")
        return plan, ta
    stage = {**ta, "stage": "Neon brain (TradingAgents not available)" if ta["status"] in ("not available", "not installed") else ta["stage"]}
    try:
        text = llm.ask("brain", model_for("strategist"), "You are the lead analyst of a trading desk.", q, schema=PLAN_SCHEMA)
        plan = parse_json(text)
        if "strategies" in plan and not plan.get("dry_run"):
            plan["source"] = "direct Gemini (" + model_for("strategist") + ")"
            return plan, {**stage, "status": "ok (direct Gemini)", "output": json.dumps(plan, indent=1)}
        raise ValueError("no plan in the answer")
    except Exception as e:
        return dict(DEFAULT_PLAN), {**stage, "status": "failed: default plan used", "output": "", "stderr": str(e)[:600]}


def plan_text(plan):
    lines = [f"Direction: {plan.get('direction')} · horizon {plan.get('horizon', 'n/a')} · source: {plan.get('source', 'n/a')}",
             f"Thesis: {plan.get('thesis', '')}", "Strategies to backtest:"]
    lines += [f"- {s.get('name', '?')}: {s.get('rules', '')}" for s in plan.get("strategies", [])[:3]]
    if plan.get("key_risks"):
        lines.append("Key risks: " + "; ".join(plan["key_risks"][:5]))
    lines.append(f"Proven wrong if: {plan.get('invalidation', 'n/a')}")
    return "\n".join(lines)
