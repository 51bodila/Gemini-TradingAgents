"""Hard rules and paper-order building, offline."""
import json
import os
from gemini_desk import rules, paper


def plan(e=100, s=95, t=112.5, d="long"):
    return {"decision": d, "entry": e, "stop": s, "target": t}


def calc(qty=20, rr=2.5, atr=1.0, pos=20.0, gap=0.1):
    return {"quantity": qty, "reward_risk": rr, "stop_in_atr": atr, "position_pct_capital": pos, "entry_vs_last_pct": gap, "position_usd": 2000}


def test_rules():
    assert rules.check(plan(), calc(), 10_000)[0] == "GO"
    assert rules.check(plan(), calc(rr=1.2), 10_000)[0] == "NO-GO"
    assert rules.check(plan(s=105), calc(), 10_000)[0] == "NO-GO"              # stop above entry on a long
    v, why, f = rules.check(plan(), calc(pos=40), 10_000)
    assert v == "GO SMALLER" and abs(f - .5) < 1e-9
    assert rules.check(plan(), calc(atr=.2), 10_000)[0] == "NO-GO"
    assert rules.combine("GO", "NO-GO") == "NO-GO" and rules.combine("GO SMALLER", "GO") == "GO SMALLER"
    open("KILL", "w").close()
    try:
        assert rules.check(plan(), calc(), 10_000)[0] == "NO-GO"
    finally:
        os.remove("KILL")


def test_paper_order():
    o, err = paper.build_order({"symbol": "AAPL", "side": "buy", "qty": 7.9, "entry": 355.5, "stop": 341.2, "target": 383.1})
    assert err is None and o["qty"] == "7" and o["order_class"] == "bracket" and o["stop_loss"]["stop_price"] == "341.20"
    assert paper.build_order({"symbol": "AAPL", "side": "buy", "qty": .4, "entry": 1, "stop": .9, "target": 1.2})[0] is None
    assert "paper-api.alpaca.markets" in paper.PAPER_ORDERS_URL and "api.alpaca.markets" not in paper.PAPER_ORDERS_URL.replace("paper-api.", "")
