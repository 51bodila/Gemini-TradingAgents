"""paper: send the research desk's target position to Alpaca PAPER trading. Never a live endpoint.

Default prints the order. With --send it posts a bracket order (limit entry, take-profit, stop-loss) to
https://paper-api.alpaca.markets using ALPACA_KEY / ALPACA_SECRET from .env (free paper account, resettable $100k).
Stocks only: Alpaca does not take bracket orders for crypto (not supported here).
"""
import json
import math
import os
import urllib.error
import urllib.request

PAPER_ORDERS_URL = "https://paper-api.alpaca.markets/v2/orders"  # paper only, by design


def _bracket(o, qty, target):
    return {"symbol": o["symbol"], "qty": str(qty), "side": o["side"], "type": "limit", "time_in_force": "day",
            "limit_price": f"{o['entry']:.2f}", "order_class": "bracket",
            "take_profit": {"limit_price": f"{target:.2f}"}, "stop_loss": {"stop_price": f"{o['stop']:.2f}"}}


def build_orders(o):
    """Half the shares take profit at Target 1, the rest at Target 2. One share: a single bracket to Target 2."""
    qty = math.floor(o["qty"])  # bracket orders need whole shares
    if qty < 1:
        return None, f"sized quantity {o['qty']:.4f} is below 1 share: no order"
    t2 = o.get("target_2", o.get("target"))
    t1 = o.get("target_1")
    if qty == 1 or t1 is None:
        return [_bracket(o, qty, t2)], None
    q1 = qty // 2
    return [_bracket(o, q1, t1), _bracket(o, qty - q1, t2)], None


def guard(orders, plan, capital, max_position_pct, url, existing_notional=0.0, open_same_side=False):
    """The AI never types the order. Returns None if every order matches the Python-validated plan, else the reason.
    Pre-trade checks after voyager67/JaneStreet-Agentic-Skills (Apache-2.0) and one order per symbol and side after
    EnriqueKhai/JaneStreetETC22 (BSD-3): ideas only, no code copied."""
    if url != PAPER_ORDERS_URL or not url.startswith("https://paper-api.alpaca.markets/"):
        return f"refused: endpoint {url} is not Alpaca PAPER"
    if open_same_side:
        return f"refused: an open {plan['side']} order for {plan['symbol']} already exists (one order per symbol and side)"
    targets = {f"{plan[k]:.2f}" for k in ("target_1", "target_2", "target") if plan.get(k) is not None}
    total = 0
    for o in orders:
        want = {"symbol": plan["symbol"], "side": plan["side"], "limit_price": f"{plan['entry']:.2f}"}
        for k, x in want.items():
            if o.get(k) != x:
                return f"refused: order {k} {o.get(k)} differs from the validated plan ({x})"
        if o["stop_loss"]["stop_price"] != f"{plan['stop']:.2f}":
            return f"refused: stop {o['stop_loss']['stop_price']} differs from the validated plan ({plan['stop']:.2f})"
        if o["take_profit"]["limit_price"] not in targets:
            return f"refused: take profit {o['take_profit']['limit_price']} is not a validated target"
        total += int(o["qty"])
    if total > math.floor(plan["qty"]):
        return f"refused: {total} shares > {math.floor(plan['qty'])} validated"
    cap = capital * max_position_pct / 100
    notional = total * plan["entry"] + existing_notional
    if notional > cap + 1e-6:
        return f"refused: new + existing exposure ${notional:,.0f} > the {max_position_pct:.0f}% cap (${cap:,.0f})"
    return None


def _alpaca(path, key, sec):
    req = urllib.request.Request("https://paper-api.alpaca.markets" + path,
                                 headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def exposure(symbol, side, key, sec):
    """(existing notional for the symbol: position + open orders, is there an open order on the same side)."""
    pos = _alpaca(f"/v2/positions/{symbol}", key, sec)
    notional = abs(float(pos.get("market_value") or 0)) if pos else 0.0
    same = False
    for o in _alpaca(f"/v2/orders?status=open&symbols={symbol}", key, sec) or []:
        notional += float(o.get("qty") or 0) * float(o.get("limit_price") or 0)
        same = same or o.get("side") == side
    return notional, same


def paper(symbol, out_dir, send=False):
    s = symbol.upper()
    f = out_dir / f"{s}-latest.order.json"
    if not f.exists():
        print(f"No research for {s} yet. Run: gemini-tradingagents {s}")
        return 1
    saved = json.loads(f.read_text())
    o = saved.get("order")
    if saved.get("dry_run"):
        print(f"Latest {s} research was a --dry-run (verdict {saved.get('final')}); run real research first.")
        return 1
    if not o:
        print(f"Latest {s} verdict ({saved.get('generated')}): {saved.get('final')}. No order.")
        return 0
    if s.endswith(("USDT", "-USD", "USDC")):
        print("Crypto: Alpaca paper bracket orders are stocks-only. Use the NautilusTrader sandbox (README, next steps).")
        return 1
    orders, err = build_orders(o)
    if err:
        print(err)
        return 0
    print(f"Alpaca PAPER orders from research {saved.get('generated')} (verdict {saved.get('final')}):")
    print(json.dumps(orders, indent=1))
    capital, max_pos = float(saved.get("capital") or 10_000), float(saved.get("max_position_pct") or 20)
    why = guard(orders, o, capital, max_pos, PAPER_ORDERS_URL)
    if why:
        print(why)
        return 1
    if not send:
        print("Not sent (dry run). Add --send to post it to your Alpaca PAPER account.")
        return 0
    key, sec = os.environ.get("ALPACA_KEY"), os.environ.get("ALPACA_SECRET")
    if not (key and sec):
        print("ALPACA_KEY / ALPACA_SECRET missing in .env (free paper account at alpaca.markets).")
        return 1
    try:
        existing, same_side = exposure(o["symbol"], o["side"], key, sec)
    except Exception as e:
        print(f"refused: could not read Alpaca positions and open orders ({str(e)[:120]}), so the cap cannot be checked")
        return 1
    why = guard(orders, o, capital, max_pos, PAPER_ORDERS_URL, existing, same_side)
    if why:
        print(why)
        return 1
    for i, order in enumerate(orders, 1):
        req = urllib.request.Request(PAPER_ORDERS_URL, data=json.dumps(order).encode(), method="POST",
                                     headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())
            print(f"Sent order {i}/{len(orders)} to Alpaca PAPER (take profit {order['take_profit']['limit_price']}): id {resp.get('id')}, status {resp.get('status')}")
        except urllib.error.HTTPError as e:
            print(f"Alpaca PAPER rejected order {i}/{len(orders)} ({e.code}): {e.read().decode(errors='ignore')[:300]}")
            return 1
    return 0
