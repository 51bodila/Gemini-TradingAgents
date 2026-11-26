"""Keep score: resolve past calls in reports/journal.csv against later daily bars.

A call is a WIN if Target 1 trades before the stop, a LOSS if the stop trades first. If both trade in the same daily
bar we cannot tell the order, so it counts as a LOSS (the cautious reading). Calls with no hit yet stay open.
The Brier score is the mean of (p_win - outcome)^2: 0 is perfect, 0.25 is a coin flip said with p = 0.5.
"""
import csv
from datetime import date
from pathlib import Path


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def calls(journal_path):
    p = Path(journal_path)
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        if r.get("final") not in ("GO", "GO SMALLER") or r.get("decision") not in ("long", "short"):
            continue
        e, s, t1, pw = _f(r.get("entry")), _f(r.get("stop")), _f(r.get("target_1")), _f(r.get("p_win"))
        if None in (e, s, t1, pw):
            continue
        try:
            d = date.fromisoformat((r.get("time_utc") or "")[:10])
        except ValueError:
            continue
        out.append({"date": d, "symbol": r["symbol"], "side": r["decision"], "entry": e, "stop": s, "t1": t1, "p": pw})
    return out


def resolve(call, bars):
    """bars: [(iso date, open, high, low, close, volume)]. Only bars after the call's date count."""
    for b in bars:
        d = date.fromisoformat(b[0])
        if d <= call["date"]:
            continue
        hi, lo = b[2], b[3]
        if call["side"] == "long":
            stop_hit, t1_hit = lo <= call["stop"], hi >= call["t1"]
        else:
            stop_hit, t1_hit = hi >= call["stop"], lo <= call["t1"]
        if stop_hit:
            return "loss", d
        if t1_hit:
            return "win", d
    return "open", None


def resolve_all(journal_path, bars_fn):
    cs = calls(journal_path)
    cache = {}
    for c in cs:
        if c["symbol"] not in cache:
            try:
                cache[c["symbol"]] = bars_fn(c["symbol"])
            except Exception:
                cache[c["symbol"]] = []
        c["outcome"], c["resolved_on"] = resolve(c, cache[c["symbol"]])
    return cs


def history(cs):
    done = [c for c in cs if c["outcome"] in ("win", "loss")]
    n = len(done)
    h = {"resolved": n, "open": len(cs) - n, "loss_streak": 0, "last_loss_date": None}
    if not n:
        return h
    y = [1.0 if c["outcome"] == "win" else 0.0 for c in done]
    h.update(hit_rate=sum(y) / n, mean_p=sum(c["p"] for c in done) / n,
             brier=sum((c["p"] - o) ** 2 for c, o in zip(done, y)) / n)
    for c in sorted(done, key=lambda c: c["resolved_on"], reverse=True):
        if c["outcome"] != "loss":
            break
        h["loss_streak"] += 1
        h["last_loss_date"] = h["last_loss_date"] or c["resolved_on"]
    return h


def table(cs):
    bins = [(0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 1.01)]
    lines = ["predicted p  | calls | hit rate"]
    for lo, hi in bins:
        g = [c for c in cs if c["outcome"] in ("win", "loss") and lo <= c["p"] < hi]
        hr = f"{sum(c['outcome'] == 'win' for c in g) / len(g):.2f}" if g else "  - "
        lines.append(f"{lo:.1f} - {min(hi, 1.0):.1f}    | {len(g):5d} | {hr}")
    return "\n".join(lines)


def report(journal_path, bars_fn):
    cs = resolve_all(journal_path, bars_fn)
    h = history(cs)
    if not cs:
        return "No GO calls in the journal yet. Every real run adds one line to reports/journal.csv."
    out = [f"Calls: {len(cs)} · resolved {h['resolved']} · open {h['open']}"]
    if h["resolved"]:
        out.append(f"Hit rate (Target 1 before stop): {h['hit_rate']:.2f} · mean predicted p: {h['mean_p']:.2f} · "
                   f"Brier score: {h['brier']:.3f} (0 = perfect, 0.25 = coin flip)")
        out.append(f"Loss streak: {h['loss_streak']}")
        out.append(table(cs))
    return "\n".join(out)
