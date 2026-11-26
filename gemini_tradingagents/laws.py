"""Trading laws: checks in plain Python that run after Carbon and after the hard rules. Like the hard rules, they can
only make a verdict stricter (NO-GO, or a smaller size), never looser.

Where they come from (none of this is an official Jane Street document; Jane Street publishes no trading rulebook):
- Jane Street's public material: its interview prep names probability, expected value and making markets; its podcast
  Signals and Threads stresses data discipline ("being sloppy with data science is fatal").
- The Laws of Trading (Wiley, 2019) by Agustin Lebron, a former Jane Street trader (paraphrased): know why you trade, adverse
  selection, take only paid risks, use the most liquid instrument, explain your edge in five minutes, costs are never
  negligible, what never happened can still happen.
- Jane Street's blog: "Mitigating memorization in LLMs" (Sep 2026) and "Flex Model" (Oct 2026).
- Standard math, labelled as such: Kelly/Thorp sizing, Brier score.
- Ideas (no code) from open-source projects: RasmusCodes/figgie-bot (MIT, pay at most value), scaomath/kaggle-jane-street
  and evgeniavolkova/kagglejanestreet (purged walk-forward with an embargo).
No code was copied from any project.
"""
import csv
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ORDER = {"NO-GO": 0, "GO SMALLER": 1, "GO": 2}

LAWS = [
    ("data", "Fail closed on bad data", "Jane Street, Signals and Threads: 'being sloppy with data science is fatal'"),
    ("why", "Know why you trade before you trade", "paraphrased from Agustin Lebron, The Laws of Trading, 2019 (ex-Jane Street)"),
    ("edge", "Explain your edge in five sentences", "paraphrased from Agustin Lebron, The Laws of Trading, 2019 (ex-Jane Street)"),
    ("other_side", "Ask who is on the other side (adverse selection)", "Jane Street, Probability & Markets guide"),
    ("two_yes", "Two independent yeses: Neon and the Argon committee agree", "repo idea (pre-trade checks)"),
    ("chase", "Don't chase: entry within 1 ATR of the last close", "Jane Street guide (adverse selection)"),
    ("cooloff", "Cool off after 3 losses in a row", "repo idea (kill hierarchy)"),
    ("score", "Keep score: correct the judge's probability by its record", "standard math (Brier score, calibration)"),
    ("ev", "Positive expected value after costs", "Jane Street guide (expected value); paraphrased from Agustin Lebron, The Laws of Trading, 2019 (ex-Jane Street)"),
    ("value", "Never pay above value", "Jane Street guide (expected value); RasmusCodes/figgie-bot idea"),
    ("kelly", "Size by edge: quarter Kelly, never above the 1% rule", "standard sizing math (Kelly/Thorp)"),
    ("paid_risk", "Take only the risks you are paid for", "paraphrased from Agustin Lebron, The Laws of Trading, 2019 (ex-Jane Street)"),
    ("memory", "The model may remember the test period", "Jane Street blog, Mitigating memorization in LLMs"),
    ("decay", "Edges decay", "standard practice (out-of-sample decay)"),
    ("embargo", "Purged walk-forward with an embargo", "kaggle-jane-street solutions (idea); Jane Street blog, Flex Model"),
    ("liquidity", "Stay small against daily volume", "paraphrased from Agustin Lebron, The Laws of Trading, 2019 (ex-Jane Street)"),
    ("tail", "Survive a gap through the stop", "paraphrased from Agustin Lebron, The Laws of Trading, 2019 (ex-Jane Street)"),
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
        "half_cut": f("GD_HALF_CUT", 0.5),                 # size factor for the 'half size' laws
        "model_cutoff": os.environ.get("GD_JS_MODEL_CUTOFF", "2026-01-01"),
        "decay_ratio": f("GD_DECAY_RATIO", 0.5),           # recent half must earn >= this share of the older half
        "min_resolved": f("GD_MIN_RESOLVED", 20.0),        # resolved calls before the judge's p is corrected
        "cooloff_losses": f("GD_COOLOFF_LOSSES", 3.0),
        "cooloff_hours": f("GD_COOLOFF_HOURS", 24.0),
    }


def committee_view(text):
    """(direction, has_bear_case) from the committee's text. direction: long, short, neutral, split or unknown."""
    t = (text or "").lower()
    i = t.rfind("pm decision")
    seg = t[i:i + 300] if i >= 0 else ""
    if not seg:
        d = "unknown"
    elif "no trade" in seg or "flat" in seg or "neutral" in seg:
        d = "neutral"
    elif "long" in seg and "short" in seg:
        d = "split"
    elif "long" in seg or "buy" in seg:
        d = "long"
    elif "short" in seg or "sell" in seg:
        d = "short"
    else:
        d = "unknown"
    j = t.find("bear")
    bear_words = len(re.findall(r"[a-z0-9%$.]+", t[j:j + 400])) if j >= 0 else 0
    return d, bear_words >= 15


def latest_date(text):
    ds = re.findall(r"\b(20\d\d-\d\d-\d\d)\b", text or "")
    out = []
    for d in ds:
        try:
            out.append(date.fromisoformat(d))
        except ValueError:
            pass
    return max(out) if out else None


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


def check(v, calc, m, capital, symbol="", today=None, committee_text=None, plan_direction=None, backtest_text="", history=None):
    """v: the judge's verdict (with target_1 / target_2), calc: sizing() output, m: data.metrics().
    committee_text: the Argon committee's output (None = committee not run). plan_direction: Neon's direction.
    backtest_text: Hydrogen's output. history: score.history() of earlier calls (None = no record yet).
    Returns (verdict, results, size_factor, numbers). results: list of {law, name, source, status, detail}.
    size_factor only ever shrinks the position; several 'half size' laws do not compound."""
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

    # two independent yeses: Neon's plan and the Argon committee
    opp = {"long": "short", "short": "long"}[v["decision"]]
    if plan_direction == opp:
        res("two_yes", "fail", f"Neon's plan is {plan_direction}, the judge wants {v['decision']}")
    elif committee_text is None:
        factor = min(factor, k["half_cut"])
        res("two_yes", "cut", f"no committee ran: one yes only, size x{k['half_cut']:.2f}")
    else:
        cdir, bear = committee_view(committee_text)
        nums["committee"] = cdir
        if cdir == opp:
            res("two_yes", "fail", f"the committee says {cdir}, the judge wants {v['decision']}")
        elif cdir in ("neutral", "split", "unknown") or not bear:
            factor = min(factor, k["half_cut"])
            why = f"committee is {cdir}" if cdir != v["decision"] else "no real bear argument (rubber stamp)"
            res("two_yes", "cut", f"{why}: size x{k['half_cut']:.2f}")
        else:
            res("two_yes", "pass", f"Neon {plan_direction or 'n/a'}, committee {cdir}, with a bear case on record")

    # 5. don't chase
    gap_atr = sg * (e - last) / atr
    nums["entry_vs_last_atr"] = gap_atr
    res("chase", "fail" if gap_atr > k["max_entry_atr"] else "pass",
        f"entry is {gap_atr:+.2f} ATR from the last close (max +{k['max_entry_atr']:.1f} in the trade direction)")

    # cool-off and calibration from the journal
    h = history or {}
    td = today or datetime.now(timezone.utc).date()
    last_loss = h.get("last_loss_date")
    if h.get("loss_streak", 0) >= k["cooloff_losses"] and last_loss and (td - last_loss) <= timedelta(hours=k["cooloff_hours"]):
        res("cooloff", "fail", f"{h['loss_streak']} losses in a row, the last on {last_loss}: no new trades for {k['cooloff_hours']:.0f}h")
    else:
        res("cooloff", "pass", f"loss streak {h.get('loss_streak', 0)}")

    cost = e * k["fee_bps"] / 10_000 + k["slippage_atr"] * atr
    cost_r = cost / R
    p_raw = _num(v.get("p_win"))
    if p_raw is None or not 0 < p_raw < 1:
        res("ev", "fail", "judge gave no win probability (p_win), so EV cannot be computed")
        return "NO-GO", out, 0.0, nums
    p_cal = p_raw
    n_res = h.get("resolved", 0)
    if n_res >= k["min_resolved"] and h.get("mean_p"):
        p_cal = min(0.99, max(0.01, p_raw * h["hit_rate"] / h["mean_p"]))
        res("score", "pass" if p_cal >= p_raw else "cut",
            f"{n_res} resolved calls: hit rate {h['hit_rate']:.2f} vs predicted {h['mean_p']:.2f}, Brier {h.get('brier', float('nan')):.3f}; "
            f"judge p {p_raw:.2f} -> {p_cal:.2f}")
        p_cal = min(p_cal, p_raw)  # the record may only lower the judge's probability
    else:
        res("score", "pass", f"{n_res} resolved calls (correction starts at {k['min_resolved']:.0f})")
    p = max(0.0, p_cal - k["p_margin"])
    # half the position exits at T1 (1R), half at T2: average win in R
    win_r = 0.5 * abs(t1 - e) / R + 0.5 * abs(t2 - e) / R
    ev_r = p * win_r - (1 - p) * 1.0 - cost_r
    nums.update(p_win=p_raw, p_used=p, avg_win_r=win_r, cost_r=cost_r, ev_r=ev_r)
    res("ev", "pass" if ev_r > 0 else "fail",
        f"EV {ev_r:+.2f}R = {p:.2f} x {win_r:.2f}R - {1 - p:.2f} x 1R - costs {cost_r:.2f}R (judge p {p_raw:.2f}, used {p:.2f})")

    # never pay above value: the entry must be no worse than p*T1 + (1-p)*stop
    value = p * t1 + (1 - p) * s
    nums["fair_value"] = value
    bad = e > value if sg > 0 else e < value
    res("value", "fail" if bad else "pass",
        f"fair value {value:,.2f} = {p:.2f} x T1 + {1 - p:.2f} x stop; entry {e:,.2f} {'pays above it' if bad else 'is within it'}")

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

    # the model may remember the test period
    cutoff = date.fromisoformat(k["model_cutoff"])
    oos = None
    try:
        oos = date.fromisoformat(str(v.get("oos_end"))[:10])
    except ValueError:
        pass
    seen = latest_date(backtest_text)
    last_oos = max([d for d in (oos, seen) if d], default=None)
    if last_oos and last_oos > cutoff:
        res("memory", "pass", f"out-of-sample data runs to {last_oos}, after the model cutoff {cutoff}")
    else:
        factor = min(factor, k["half_cut"])
        res("memory", "cut", f"no out-of-sample data after the model cutoff {cutoff}: the model may remember this period, size x{k['half_cut']:.2f}")

    # edges decay: the recent half of the backtest must keep at least half of the older half's return
    rec, old = _num(v.get("backtest_recent_return")), _num(v.get("backtest_older_return"))
    if rec is None or old is None:
        factor = min(factor, k["half_cut"])
        res("decay", "cut", f"backtest halves not reported: size x{k['half_cut']:.2f}")
    elif rec <= 0 or (old > 0 and rec < k["decay_ratio"] * old):
        factor = min(factor, k["half_cut"])
        res("decay", "cut", f"recent half {rec:+.2%} vs older half {old:+.2%}: the edge is fading, size x{k['half_cut']:.2f}")
    else:
        res("decay", "pass", f"recent half {rec:+.2%} vs older half {old:+.2%}")

    # purged walk-forward: embargo >= max(lookback, holding horizon) bars between train and test
    emb, look, hor = _num(v.get("embargo_bars")), _num(v.get("max_lookback_bars")), _num(v.get("horizon_bars"))
    need = max([x for x in (look, hor) if x is not None], default=None)
    if emb is None or need is None:
        factor = min(factor, k["half_cut"])
        res("embargo", "cut", f"embargo or lookback not reported: size x{k['half_cut']:.2f}")
    elif emb < need:
        factor = min(factor, k["half_cut"])
        res("embargo", "cut", f"embargo {emb:.0f} bars < needed {need:.0f}: train and test may overlap, size x{k['half_cut']:.2f}")
    else:
        res("embargo", "pass", f"embargo {emb:.0f} bars >= {need:.0f} (max of lookback and horizon)")

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
