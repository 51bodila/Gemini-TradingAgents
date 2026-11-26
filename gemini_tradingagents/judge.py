"""Carbon: the final judge, built on Google's Agent Development Kit (google/adk-python, Apache-2.0).

It reads the three repos' outputs plus numbers computed in Python and proposes one target position.
Hard Python rules (rules.py) run on that proposal afterwards and can only make it stricter.
If google-adk is not installed, the same prompt goes through gemini_tradingagents.llm (plain HTTPS).
"""
import asyncio
import json

from .llm import parse_json
from .roles import model_for

SCHEMA = {"type": "OBJECT", "properties": {
    "verdict": {"type": "STRING", "enum": ["GO", "NO-GO", "GO SMALLER"]},
    "decision": {"type": "STRING", "enum": ["long", "short", "no trade"]},
    "entry": {"type": "NUMBER", "nullable": True}, "stop": {"type": "NUMBER", "nullable": True}, "target": {"type": "NUMBER", "nullable": True},
    "reasons": {"type": "ARRAY", "items": {"type": "STRING"}}, "conflicts": {"type": "ARRAY", "items": {"type": "STRING"}},
    "fixes": {"type": "ARRAY", "items": {"type": "STRING"}},
    "p_win": {"type": "NUMBER", "nullable": True}, "thesis": {"type": "STRING"}, "edge": {"type": "STRING"},
    "other_side": {"type": "STRING"}, "invalidation": {"type": "STRING"},
    "paid_risks": {"type": "ARRAY", "items": {"type": "STRING"}}, "unpaid_risks": {"type": "ARRAY", "items": {"type": "STRING"}},
    "confidence": {"type": "STRING", "enum": ["low", "medium", "high"]}},
    "required": ["verdict", "decision", "reasons", "p_win", "thesis", "edge", "other_side", "invalidation", "unpaid_risks"]}

INSTRUCTION = """You are the risk manager and final judge of a trading research desk. Three independent systems studied
the same asset: Vibe-Trading (backtests and validation), ai-hedge-fund (an investor committee) and TradingAgents (deep
research with sources). You also get price metrics computed in Python and the desk's hard rules.
Decide ONE target position or no trade. Rules:
- Use only numbers that appear in the inputs. Never invent prices or results.
- If the systems disagree, say where in `conflicts` and lean to the more cautious reading.
- A backtest that fails its walk-forward or Monte Carlo check is a reason for NO-GO.
- The stop must sit beyond normal noise (compare with ATR14) and reward:risk must be at least the rule minimum.
- Hard rules are binding: you may be stricter, never looser.
Trading laws (checked again in Python after you; a missing field means NO-GO):
- Know why you trade: `thesis` in one or two sentences and `invalidation`, the price or event that proves it wrong.
- Explain the edge in at most five sentences (`edge`). A backtest or a model is not an edge; say why the market is wrong.
- Adverse selection: `other_side` says who is selling to you (or buying from you) and why they are willing to.
  If the answer is "someone who knows more", do not trade.
- `p_win`: your calibrated probability (0-1) that Target 1 is hit before the stop. Most real edges are 0.40-0.60.
  Python subtracts a humility margin and requires positive expected value after fees and slippage.
- Take only the risks you are paid for: list them in `paid_risks`; anything else that could hit the trade (earnings,
  macro event, unlock, gap risk) goes in `unpaid_risks`. Each unpaid risk halves the size.
- Data discipline: a backtest with under 30 trades, no costs, no out-of-sample or walk-forward window, or signals that
  use the same bar they trade, is not evidence. Say so in `reasons`.
- What never happened can still happen: prefer liquid assets and stops that survive a gap.
Return JSON: verdict, decision, entry, stop, target, p_win, thesis, edge, other_side, invalidation, paid_risks,
unpaid_risks, confidence, reasons (3-6, each citing a number and its source system), conflicts, fixes."""


def _prompt(sym, metrics_txt, stages, mandate):
    parts = [f"ASSET {sym}", f"PRICE METRICS (Python)\n{metrics_txt}", f"HARD RULES\n{json.dumps(mandate, indent=1)}"]
    for s in stages:
        body = s["output"] or f"(no output: {s['status']}; {s.get('stderr', '')[:300]})"
        parts.append(f"=== {s['stage']} ({s.get('model', '')}) status={s['status']} ===\n{body}")
    return "\n\n".join(parts)


async def _adk(model, prompt):
    import os
    # AI Studio key, not Vertex AI
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
    if not os.environ.get("GOOGLE_API_KEY") and os.environ.get("GEMINI_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent = LlmAgent(name="carbon_judge", model=model, instruction=INSTRUCTION, output_schema=SCHEMA)
    runner = InMemoryRunner(agent=agent, app_name="gemini-tradingagents")
    session = await runner.session_service.create_session(app_name="gemini-tradingagents", user_id="desk")
    text = ""
    async for ev in runner.run_async(user_id="desk", session_id=session.id,
                                     new_message=types.Content(role="user", parts=[types.Part(text=prompt)])):
        if ev.is_final_response() and ev.content and ev.content.parts:
            text = "".join(p.text or "" for p in ev.content.parts)
    return text


def judge(llm, sym, metrics_txt, stages, mandate, dry_run=False):
    """Returns (verdict dict, engine name)."""
    model = model_for("judge")
    prompt = _prompt(sym, metrics_txt, stages, mandate)
    if dry_run:
        return parse_json(llm.ask("judge", model, INSTRUCTION, prompt, schema=SCHEMA)), "dry-run"
    try:
        import google.adk  # noqa: F401
    except ImportError:
        return parse_json(llm.ask("judge", model, INSTRUCTION, prompt, schema=SCHEMA)), "gemini_tradingagents.llm (google-adk not installed)"
    text = asyncio.run(_adk(model, prompt))
    llm.usage.add("judge (ADK; tokens in ADK logs)", model, 0, 0, 0.0)
    return parse_json(text), "google-adk LlmAgent"
