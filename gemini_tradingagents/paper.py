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


def build_order(o):
    qty = math.floor(o["qty"])  # bracket orders need whole shares
    if qty < 1:
        return None, f"sized quantity {o['qty']:.4f} is below 1 share: no order"
    return {"symbol": o["symbol"], "qty": str(qty), "side": o["side"], "type": "limit", "time_in_force": "day",
            "limit_price": f"{o['entry']:.2f}", "order_class": "bracket",
            "take_profit": {"limit_price": f"{o['target']:.2f}"}, "stop_loss": {"stop_price": f"{o['stop']:.2f}"}}, None


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
    if s.endswith("USDT"):
        print("Crypto: Alpaca paper bracket orders are stocks-only. Use the NautilusTrader sandbox (README, next steps).")
        return 1
    order, err = build_order(o)
    if err:
        print(err)
        return 0
    print(f"Alpaca PAPER order from research {saved.get('generated')} (verdict {saved.get('final')}):")
    print(json.dumps(order, indent=1))
    if not send:
        print("Not sent (dry run). Add --send to post it to your Alpaca PAPER account.")
        return 0
    key, sec = os.environ.get("ALPACA_KEY"), os.environ.get("ALPACA_SECRET")
    if not (key and sec):
        print("ALPACA_KEY / ALPACA_SECRET missing in .env (free paper account at alpaca.markets).")
        return 1
    req = urllib.request.Request(PAPER_ORDERS_URL, data=json.dumps(order).encode(), method="POST",
                                 headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
        print(f"Sent to Alpaca PAPER: id {resp.get('id')}, status {resp.get('status')}")
    except urllib.error.HTTPError as e:
        print(f"Alpaca PAPER rejected the order ({e.code}): {e.read().decode(errors='ignore')[:300]}")
        return 1
    return 0
