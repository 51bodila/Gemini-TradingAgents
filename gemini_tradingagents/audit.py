"""audit: a second pair of eyes on a strategy and its backtest.

Neon reads the code and report and lists suspected bugs; Carbon checks each claim against the code and gives GO / NO-GO.
The author model (whoever wrote the strategy) should not be the one grading it.
"""
import json
from pathlib import Path

from .llm import parse_json
from .roles import model_for

_S = {"type": "STRING"}
FINDING = {"type": "OBJECT", "properties": {"severity": {"type": "STRING", "enum": ["critical", "major", "minor"]}, "category": _S, "where": _S,
           "issue": _S, "why_it_matters": _S, "fix": _S}, "required": ["severity", "where", "issue"]}
FINDINGS_SCHEMA = {"type": "OBJECT", "properties": {"findings": {"type": "ARRAY", "items": FINDING}}, "required": ["findings"]}
AUDIT_VERDICT_SCHEMA = {"type": "OBJECT", "properties": {"confirmed": {"type": "ARRAY", "items": FINDING},
                        "rejected": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"where": _S, "reason": _S}}},
                        "verdict": {"type": "STRING", "enum": ["GO", "NO-GO", "FIX FIRST"]}, "summary": _S}, "required": ["confirmed", "verdict", "summary"]}

CHECKLIST = """Check for, and cite file:line for each finding:
1. Lookahead: using a bar's close/high/low before that bar is complete, future data in indicators, shifted joins, survivorship.
2. Impossible fills: filling limit orders at touch without queue position, trading at prices outside the bar, ignoring spread.
3. Costs: missing or wrong fees, slippage, funding, borrow.
4. Overfitting: many tuned parameters vs few trades, no out-of-sample period, cherry-picked dates.
5. Risk: no position cap, no stop, leverage, position sizing using future equity.
6. Report sanity: Sharpe/returns that are implausible for the trade count and costs."""


def audit(llm, code_paths, report_path=None, max_chars=180_000):
    parts = []
    for p in code_paths:
        txt = Path(p).read_text(encoding="utf-8", errors="ignore")
        numbered = "\n".join(f"{i + 1:5d}  {line}" for i, line in enumerate(txt.splitlines()))
        parts.append(f"=== FILE {p} ===\n{numbered}")
    code = "\n\n".join(parts)[:max_chars]
    report = Path(report_path).read_text(encoding="utf-8", errors="ignore")[:40_000] if report_path else "(no backtest report given)"

    findings = parse_json(llm.ask("auditor", model_for("strategist"),
                                  "You audit trading strategies for a quant desk. You are skeptical and precise. Only report issues you can point to in the code or report.",
                                  f"{CHECKLIST}\n\nBACKTEST REPORT\n{report}\n\nCODE\n{code}\n\n"
                                  "Return JSON: findings = list of {severity: 'critical'|'major'|'minor', category, where: 'file:line', issue, why_it_matters, fix}.",
                                  schema=FINDINGS_SCHEMA))

    verdict = parse_json(llm.ask("judge", model_for("judge"),
                                 "You are the final reviewer. Verify each finding against the code: keep the real ones, drop the false alarms. Then decide.",
                                 f"FINDINGS\n{json.dumps(findings, indent=1)}\n\nCODE\n{code}\n\nREPORT\n{report}\n\n"
                                 "Return JSON: confirmed (list of findings you verified, same shape), rejected (list of {where, reason}), "
                                 "verdict ('GO'|'NO-GO'|'FIX FIRST'), summary (2 sentences).", schema=AUDIT_VERDICT_SCHEMA))
    return findings, verdict


def audit_md(findings, verdict, usage_table):
    rows = verdict.get("confirmed") or []
    tab = "\n".join(f"| {f.get('severity', '')} | {f.get('category', '')} | {f.get('where', '')} | {f.get('issue', '')} | {f.get('fix', '')} |" for f in rows)
    rej = "\n".join(f"- {r.get('where', '')}: {r.get('reason', '')}" for r in (verdict.get("rejected") or [])) or "- none"
    return f"""# Strategy audit

Auditor: {model_for('strategist')}. Final reviewer: {model_for('judge')}.

## Verdict: **{verdict.get('verdict', 'n/a')}**
{verdict.get('summary', '')}

## Confirmed findings
| Severity | Category | Where | Issue | Fix |
|---|---|---|---|---|
{tab or '| | | | none confirmed | |'}

## Rejected as false alarms
{rej}

## Cost of this audit
{usage_table}
"""
