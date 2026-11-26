"""Trading laws: checks in plain Python that run after Carbon and after the hard rules. Like the hard rules, they can
only make a verdict stricter (NO-GO, or a smaller size), never looser.

Where they come from (none of this is an official Jane Street document; Jane Street publishes no trading rulebook):
- Jane Street's public material: its interview prep names probability, expected value and making markets; its podcast
  Signals and Threads stresses data discipline ("being sloppy with data science is fatal").
- The Laws of Trading (Wiley, 2019) by Agustin Lebron, a former Jane Street trader: know why you trade, adverse
  selection, take only paid risks, use the most liquid instrument, explain your edge in five minutes, costs are never
  negligible, what never happened can still happen.
- General practice, labelled as such: fractional Kelly sizing, fail closed on missing or stale data, audit log.
Ideas only; no code was copied from any project.
"""
import csv
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path

ORDER = {"NO-GO": 0, "GO SMALLER": 1, "GO": 2}

LAWS = [
    ("data", "Fail closed on bad data", "general practice; Signals and Threads (Jane Street podcast)"),
    ("why", "Know why you trade before you trade", "Lebron, The Laws of Trading, law 1"),
    ("edge", "Explain your edge in five sentences", "Lebron, law 5"),
    ("other_side", "Ask who is on the other side (adverse selection)", "Lebron, law 2"),
    ("chase", "Don't chase: entry within 1 ATR of the last close", "adverse selection, Lebron law 2"),
    ("ev", "Positive expected value after costs", "Jane Street interview prep (expected value); Lebron law 7"),
    ("kelly", "Size by edge: quarter Kelly, never above the 1% rule", "general practice"),
    ("paid_risk", "Take only the risks you are paid for", "Lebron, law 3"),
    ("liquidity", "Stay small against daily volume", "Lebron, law 4"),
    ("tail", "Survive a gap through the stop", "Lebron, law 8"),
]


def mandate():
    f = lambda k, d: float(os.environ.get(k, d))
    return {
        "fee_bps": f("GD_FEE_BPS", 10.0),                  # round-trip fees, basis points of the position
        "slippage_atr": f("GD_SLIPPAGE_ATR", 0.10),        # round-trip slippage + spread, in ATR
        "p_margin": f("GD_P_MARGIN", 0.05),                # humility: subtract from the judge's win probability
        "kelly_fraction": f("GD_KELLY_FRACTION", 0.25),    # quarter Kelly
        "max_entry_atr": f("GD_MAX_ENTRY_ATR", 1.0),       # entry no further than this from the last close
        "max_adv_pct": f("GD_MAX_ADV_PCT", 1.0),           # position <= this % of 20-day average dollar volume
        "gap_atr": f("GD_GAP_ATR", 2.0),                   # stress: price gaps this many ATR past the stop
        "max_gap_loss_pct": f("GD_MAX_GAP_LOSS_PCT", 3.0),  # loss in that gap <= this % of capital
        "max_data_age_days": f("GD_MAX_DATA_AGE_DAYS", 4.0),
        "unpaid_risk_cut": f("GD_UNPAID_RISK_CUT", 0.5),   # size factor when the judge lists unpaid risks
        "max_edge_sentences": f("GD_MAX_EDGE_SENTENCES", 5.0),
    }


def _num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _sentences(text):
    return len([s for s in str(text).replace("!", ".").replace("?", ".").split(".") if s.strip()])


def dollar_volume(symbol, m):
    """Average daily dollar volume. Yahoo reports crypto (BTC-USD) volume in dollars already; Binance pairs and stocks in units."""
    v, last = _num(m.get("avg_volume_20d")), _num(m.get("last_close"))
    if v is None or last is None:
        return None
    return v if symbol.upper().endswith("-USD") else v * last


def check(v, calc, m, capital, symbol="", today=None):
    """v: the judge's verdict (with target_1 / target_2), calc: sizing() output, m: data.metrics().
    Returns (verdict, results, size_factor, numbers). results: list of {law, name, source, status, detail}."""
    k = mandate()
    out, verdict, factor, nums = [], "GO", 1.0, {}

    def res(key, status, detail):
        nonlocal verdict
        name, src = next((n, s) for kk, n, s in LAWS if kk == key)
        out.append({"law": key, "name": name, "source": src, "status": status, "detail": detail})
        if status == "fail":
            verdict = "NO-GO"
        elif status == "cut" and verdict == "GO":
            verdict = "GO SMALLER"

    if v.get("decision") not in ("long", "short"):
        res("why", "fail", "no trade proposed")
        return "NO-GO", out, 0.0, nums

    e, s, t1, t2 = (_num(v.get(x)) for x in ("entry", "stop", "target_1", "target_2"))
    atr, last = _num(m.get("atr14")), _num(m.get("last_close"))

    # 1. data: fail closed
    problems = []
    if None in (e, s, t1, t2):
        problems.append("entry, stop or targets missing")
    if atr is None or atr <= 0 or last is None:
        problems.append("ATR14 or last close missing")
    try:
        age = ((today or datetime.now(timezone.utc).date()) - date.fromisoformat(str(m.get("date")))).days
        if age > k["max_data_age_days"]:
            problems.append(f"last bar is {age} days old")
    except (TypeError, ValueError):
        problems.append("no date on the last bar")
    res("data", "fail" if problems else "pass", "; ".join(problems) or f"last bar {m.get('date')}, ATR14 {atr:,.2f}")
    if problems:
        return "NO-GO", out, 0.0, nums

    sg = 1 if v["decision"] == "long" else -1
    R = abs(e - s)

    # 2-4. the judge must say why, what the edge is, and who is on the other side
    why = str(v.get("thesis") or "").strip()
    res("why", "pass" if why and str(v.get("invalidation") or "").strip() else "fail",
        why[:160] if why else "no thesis or no invalidation from the judge")
    edge = str(v.get("edge") or "").strip()
    n = _sentences(edge)
    res("edge", "pass" if edge and n <= k["max_edge_sentences"] else "fail",
        f"{n} sentence(s): {edge[:160]}" if edge else "no edge stated")
    other = str(v.get("other_side") or "").strip()
    res("other_side", "pass" if other else "fail", other[:160] or "judge did not say who takes the other side")

    # 5. don't chase
    gap_atr = sg * (e - last) / atr
    nums["entry_vs_last_atr"] = gap_atr
    res("chase", "fail" if gap_atr > k["max_entry_atr"] else "pass",
        f"entry is {gap_atr:+.2f} ATR from the last close (max +{k['max_entry_atr']:.1f} in the trade direction)")

    # 6. expected value after costs, in R
    cost = e * k["fee_bps"] / 10_000 + k["slippage_atr"] * atr
    cost_r = cost / R
    p_raw = _num(v.get("p_win"))
    if p_raw is None or not 0 < p_raw < 1:
        res("ev", "fail", "judge gave no win probability (p_win), so EV cannot be computed")
        return "NO-GO", out, 0.0, nums
    p = max(0.0, p_raw - k["p_margin"])
    # half the position exits at T1 (1R), half at T2: average win in R
    win_r = 0.5 * abs(t1 - e) / R + 0.5 * abs(t2 - e) / R
    ev_r = p * win_r - (1 - p) * 1.0 - cost_r
    nums.update(p_win=p_raw, p_used=p, avg_win_r=win_r, cost_r=cost_r, ev_r=ev_r)
    res("ev", "pass" if ev_r > 0 else "fail",
        f"EV {ev_r:+.2f}R = {p:.2f} x {win_r:.2f}R - {1 - p:.2f} x 1R - costs {cost_r:.2f}R (judge p {p_raw:.2f} minus {k['p_margin']:.2f})")

    # 7. quarter Kelly, capped by the 1% rule
    net_b = max(win_r - cost_r, 1e-9)
    kelly = p - (1 - p) / net_b
    risk_pct = kelly * k["kelly_fraction"] * 100
    nums.update(kelly=kelly, kelly_risk_pct=risk_pct)
    base_risk_pct = calc.get("risk_usd", 0) / capital * 100 if calc else 1.0
    if kelly <= 0:
        res("kelly", "fail", f"Kelly fraction {kelly:.3f} <= 0: no edge to size")
    elif risk_pct < base_risk_pct:
        f = risk_pct / base_risk_pct
        factor = min(factor, f)
        res("kelly", "cut", f"quarter Kelly risks {risk_pct:.2f}% of capital < the {base_risk_pct:.2f}% rule: size x{f:.2f}")
    else:
        res("kelly", "pass", f"quarter Kelly allows {risk_pct:.2f}% risk; the {base_risk_pct:.2f}% rule is the ceiling")

    # 8. paid risks only
    raw = v.get("unpaid_risks") or []
    unpaid = [str(x) for x in ([raw] if isinstance(raw, str) else raw) if str(x).strip()]
    if unpaid:
        factor = min(factor, k["unpaid_risk_cut"])
        res("paid_risk", "cut", f"unpaid risks: {'; '.join(unpaid)[:160]} -> size x{k['unpaid_risk_cut']:.2f}")
    else:
        res("paid_risk", "pass", "judge listed no unpaid risks")

    qty = (calc or {}).get("quantity", 0) * factor
    # 9. liquidity
    dv = dollar_volume(symbol, m)
    pos = qty * e
    if dv:
        pct = pos / dv * 100
        nums["pct_of_adv"] = pct
        if pct > k["max_adv_pct"]:
            f = k["max_adv_pct"] / pct
            factor *= f
            qty *= f
            res("liquidity", "cut", f"position is {pct:.3f}% of daily dollar volume > {k['max_adv_pct']}%: size x{f:.2f}")
        else:
            res("liquidity", "pass", f"position is {pct:.4f}% of 20-day average dollar volume")
    else:
        res("liquidity", "fail", "no volume data: cannot check liquidity")

    # 10. tail: a gap through the stop
    gap_loss = qty * (R + k["gap_atr"] * atr)
    gap_pct = gap_loss / capital * 100
    nums["gap_loss_pct"] = gap_pct
    if gap_pct > k["max_gap_loss_pct"]:
        f = k["max_gap_loss_pct"] / gap_pct
        factor *= f
        res("tail", "cut", f"a {k['gap_atr']:.0f} ATR gap past the stop loses {gap_pct:.2f}% > {k['max_gap_loss_pct']}%: size x{f:.2f}")
    else:
        res("tail", "pass", f"a {k['gap_atr']:.0f} ATR gap past the stop loses {gap_pct:.2f}% of capital")

    if verdict == "NO-GO":
        factor = 0.0
    return verdict, out, factor, nums


def combine(a, b):
    return a if ORDER.get(a, 0) <= ORDER.get(b, 0) else b


def journal(path, r):
    """Audit log: one line per run with the verdicts, the laws that bit and the judge's probability."""
    p = Path(path)
    new = not p.exists()
    lw = r.get("laws") or {}
    j = r.get("judge") or {}
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time_utc", "symbol", "final", "judge", "rules", "laws", "decision", "entry", "stop", "target_1", "target_2",
                        "p_win", "ev_r", "qty", "laws_not_passed"])
        n = lw.get("numbers", {})
        w.writerow([r.get("generated"), r.get("symbol"), r.get("final"), j.get("verdict"), (r.get("rules") or {}).get("verdict"),
                    lw.get("verdict"), j.get("decision"), j.get("entry"), j.get("stop"), j.get("target_1"), j.get("target_2"),
                    j.get("p_win"), f"{n['ev_r']:.3f}" if "ev_r" in n else "", (r.get("order") or {}).get("qty", 0),
                    "; ".join(f"{x['law']}={x['status']}" for x in lw.get("results", []) if x["status"] != "pass")])
