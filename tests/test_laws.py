"""Trading laws, offline: each law can block or shrink a trade, none can loosen one."""
from datetime import date

from gemini_tradingagents import desk, laws, paper, score

TODAY = date(2026, 11, 26)
M = {"atr14": 2.0, "last_close": 100.0, "date": "2026-11-25", "avg_volume_20d": 5_000_000}
COMMITTEE = ("BULL: trend up. BEAR: valuation is stretched, insiders sold 2% last quarter, volume is falling on up days "
             "and a retest of 96 is likely. RISK: gap. PM DECISION: long, size small")
BACKTEST = "Walk-forward windows 2025-01-02 to 2026-10-30, out of sample ends 2026-10-30."


def verdict(**kw):
    v = {"decision": "long", "entry": 100.0, "stop": 97.0, "target": 107.5, "p_win": 0.58,
         "thesis": "Pullback to SMA50 in an uptrend.", "edge": "Index rebalancing buyers arrive next week. Sellers are forced.",
         "other_side": "forced sellers from a fund redemption", "invalidation": "close below 96", "paid_risks": ["trend"], "unpaid_risks": [],
         "oos_end": "2026-10-30", "backtest_recent_return": 0.06, "backtest_older_return": 0.08, "embargo_bars": 60,
         "max_lookback_bars": 50, "horizon_bars": 20}
    v.update(kw)
    return desk.add_targets(v)


def run(v, m=M, capital=10_000, sym="TEST", committee=COMMITTEE, plan="long", backtest=BACKTEST, history=None):
    calc = desk.sizing(v, m, capital)
    return laws.check(v, calc, m, capital, sym, today=TODAY, committee_text=committee, plan_direction=plan,
                      backtest_text=backtest, history=history)


def status(results, law):
    return next(x["status"] for x in results if x["law"] == law)


def detail(results, law):
    return next(x["detail"] for x in results if x["law"] == law)


def test_good_trade_passes_every_law():
    v, res, f, n = run(verdict())
    assert v == "GO" and f == 1.0, [x for x in res if x["status"] != "pass"]
    assert n["ev_r"] > 0 and n["kelly"] > 0
    assert {x["law"] for x in res} == {k for k, _, _ in laws.LAWS}


def test_sources_are_labelled_honestly():
    src = {k: s for k, _, s in laws.LAWS}
    assert "Kelly/Thorp" in src["kelly"] and "Jane Street" not in src["kelly"]
    assert all("Lebron" in src[k] and "ex-Jane Street" in src[k] for k in ("why", "edge", "paid_risk", "liquidity", "tail"))


def test_fail_closed_on_stale_or_missing_data():
    assert run(verdict(), {**M, "date": "2026-11-01"})[0] == "NO-GO"
    assert run(verdict(), {**M, "atr14": float("nan")})[0] == "NO-GO"
    assert run(verdict(entry=None))[0] == "NO-GO"


def test_must_know_why_edge_and_other_side():
    assert status(run(verdict(thesis=""))[1], "why") == "fail"
    assert status(run(verdict(invalidation=""))[1], "why") == "fail"
    assert status(run(verdict(edge=""))[1], "edge") == "fail"
    assert status(run(verdict(edge="One. Two. Three. Four. Five. Six."))[1], "edge") == "fail"   # more than five sentences
    assert status(run(verdict(other_side=""))[1], "other_side") == "fail"


def test_two_independent_yeses():
    assert run(verdict(), plan="short")[0] == "NO-GO"                                           # Neon disagrees
    assert run(verdict(), committee="BEAR: long text here would not matter. PM DECISION: short")[0] == "NO-GO"
    v, res, f, _ = run(verdict(), committee=COMMITTEE.replace("PM DECISION: long", "PM DECISION: no trade"))
    assert status(res, "two_yes") == "cut" and f == 0.5
    v, res, f, _ = run(verdict(), committee="BULL: great. PM DECISION: long")                   # no bear case: rubber stamp
    assert status(res, "two_yes") == "cut" and "rubber stamp" in detail(res, "two_yes")
    assert status(run(verdict(), committee=None)[1], "two_yes") == "cut"                         # committee did not run
    assert laws.committee_view("x PM DECISION: long and short legs")[0] == "split"


def test_no_chasing():
    v, res, _, n = run(verdict(entry=103.0, stop=100.0, target=110.5))   # 1.5 ATR above the last close on a long
    assert v == "NO-GO" and status(res, "chase") == "fail" and n["entry_vs_last_atr"] > 1


def test_expected_value_must_be_positive_after_costs():
    v, res, _, n = run(verdict(p_win=0.30))
    assert v == "NO-GO" and status(res, "ev") == "fail" and n["ev_r"] < 0
    assert run(verdict(p_win=None))[0] == "NO-GO"                       # no probability: no EV, fail closed


def test_never_pay_above_value():
    v, res, _, n = run(verdict(p_win=0.52))    # p used 0.47: fair value 99.82 < entry 100 on a long
    assert status(res, "value") == "fail" and v == "NO-GO" and n["fair_value"] < 100
    v, res, _, n = run(verdict(decision="short", stop=103.0, target=92.5, p_win=0.52), plan="short",
                       committee=COMMITTEE.replace("PM DECISION: long", "PM DECISION: short"))
    assert status(res, "value") == "fail" and n["fair_value"] > 100


def test_quarter_kelly_only_shrinks(monkeypatch):
    monkeypatch.setenv("GD_KELLY_FRACTION", "0.03")
    v, res, f, n = run(verdict())
    assert status(res, "kelly") == "cut" and 0 < f < 1 and v == "GO SMALLER"
    assert n["kelly_risk_pct"] < 1.0


def test_unpaid_risk_halves_size():
    v, res, f, _ = run(verdict(unpaid_risks=["earnings in 3 days"]))
    assert v == "GO SMALLER" and status(res, "paid_risk") == "cut" and abs(f - 0.5) < 1e-9
    assert abs(run(verdict(unpaid_risks="earnings in 3 days"))[2] - 0.5) < 1e-9     # a plain string is one risk, not 18


def test_half_size_laws_do_not_compound():
    v, res, f, _ = run(verdict(unpaid_risks=["earnings"], oos_end=None, backtest_recent_return=None), backtest="")
    assert {status(res, x) for x in ("paid_risk", "memory", "decay")} == {"cut"} and f == 0.5


def test_memorization_guard():
    v, res, f, _ = run(verdict(oos_end="2025-12-31"), backtest="windows 2024-01-02 to 2025-12-31")
    assert status(res, "memory") == "cut" and f == 0.5
    assert status(run(verdict(oos_end=None), backtest="test ends 2026-06-30")[1], "memory") == "pass"


def test_edges_decay():
    assert status(run(verdict(backtest_recent_return=0.03, backtest_older_return=0.10))[1], "decay") == "cut"
    assert status(run(verdict(backtest_recent_return=-0.01, backtest_older_return=-0.05))[1], "decay") == "cut"
    assert status(run(verdict(backtest_recent_return=None))[1], "decay") == "cut"
    assert status(run(verdict(backtest_recent_return=0.06, backtest_older_return=-0.02))[1], "decay") == "pass"


def test_purged_walk_forward_embargo():
    assert status(run(verdict(embargo_bars=10))[1], "embargo") == "cut"               # 10 < max(50, 20)
    assert status(run(verdict(embargo_bars=None))[1], "embargo") == "cut"
    assert status(run(verdict(embargo_bars=50))[1], "embargo") == "pass"


def test_liquidity_cap():
    v, res, f, n = run(verdict(), {**M, "avg_volume_20d": 1_000})       # $100k a day traded
    assert status(res, "liquidity") == "cut" and f < 0.5 and n["pct_of_adv"] > 1


def test_crypto_volume_is_already_in_dollars():
    assert laws.dollar_volume("BTC-USD", {"avg_volume_20d": 3e10, "last_close": 90_000}) == 3e10
    assert laws.dollar_volume("NVDA", {"avg_volume_20d": 2e8, "last_close": 150}) == 3e10


def test_tail_gap_through_stop():
    # stop 0.75 ATR away: 1% risk buys a big position, a 2 ATR gap would lose ~3.7%
    v, res, f, n = run(verdict(entry=100.0, stop=98.5, target=103.75))
    assert status(res, "tail") == "cut" and n["gap_loss_pct"] > 3 and f < 1


def test_laws_never_loosen():
    assert laws.combine("GO SMALLER", "GO") == "GO SMALLER" and laws.combine("GO", "NO-GO") == "NO-GO"


def test_judge_cannot_change_limits():
    from gemini_tradingagents import rules
    from gemini_tradingagents.judge import SCHEMA
    assert "max_risk_pct" not in SCHEMA["properties"] and "kill_switch_file" not in SCHEMA["properties"]
    assert rules.mandate()["max_risk_pct"] == 1.0          # read from the environment only


# ---- keep score

def _journal(tmp_path, rows):
    import csv
    p = tmp_path / "journal.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_utc", "symbol", "final", "decision", "entry", "stop", "target_1", "p_win"])
        w.writerows(rows)
    return p


def test_score_resolves_calls_and_same_bar_is_a_loss(tmp_path):
    p = _journal(tmp_path, [["2026-11-01 10:00 UTC", "AAA", "GO", "long", 100, 97, 103, 0.6],
                            ["2026-11-01 10:00 UTC", "BBB", "GO", "long", 100, 97, 103, 0.6],
                            ["2026-11-01 10:00 UTC", "CCC", "GO", "short", 100, 103, 97, 0.5],
                            ["2026-11-01 10:00 UTC", "DDD", "NO-GO", "long", 100, 97, 103, 0.6]])
    bars = {"AAA": [("2026-11-01", 0, 110, 90, 0, 0), ("2026-11-02", 0, 104, 99, 0, 0)],       # first bar ignored, then T1: win
            "BBB": [("2026-11-02", 0, 104, 96, 0, 0)],                                         # both in one bar: loss
            "CCC": [("2026-11-02", 0, 101, 99, 0, 0)]}                                         # still open
    cs = score.resolve_all(p, lambda s: bars[s])
    assert [c["outcome"] for c in cs] == ["win", "loss", "open"]
    h = score.history(cs)
    assert h["resolved"] == 2 and h["hit_rate"] == 0.5 and abs(h["brier"] - (0.16 + 0.36) / 2) < 1e-9
    assert "Brier" in score.report(p, lambda s: bars[s])


def test_record_lowers_the_judges_probability():
    h = {"resolved": 25, "hit_rate": 0.40, "mean_p": 0.60, "brier": 0.3, "loss_streak": 0, "last_loss_date": None}
    v, res, _, n = run(verdict(p_win=0.70), history=h)
    assert status(res, "score") == "cut" and abs(n["p_used"] - (0.70 * 0.40 / 0.60 - 0.05)) < 1e-9
    h["hit_rate"] = 0.9                                      # a good record never raises p above the judge's
    assert abs(run(verdict(p_win=0.70), history=h)[3]["p_used"] - 0.65) < 1e-9


def test_cool_off_after_three_losses():
    h = {"resolved": 3, "loss_streak": 3, "last_loss_date": date(2026, 11, 25)}
    assert status(run(verdict(), history=h)[1], "cooloff") == "fail"
    h["last_loss_date"] = date(2026, 11, 20)
    assert status(run(verdict(), history=h)[1], "cooloff") == "pass"


# ---- the AI never types the order

PLAN = {"symbol": "AAPL", "side": "buy", "qty": 7.9, "entry": 100.0, "stop": 97.0, "target_1": 103.0, "target_2": 107.5, "target": 107.5}


def test_order_guard_accepts_the_validated_plan():
    orders, _ = paper.build_orders(PLAN)
    assert paper.guard(orders, PLAN, 10_000, 20, paper.PAPER_ORDERS_URL) is None


def test_order_guard_refuses_anything_else():
    orders, _ = paper.build_orders(PLAN)
    bad = [dict(orders[0], limit_price="101.00")] + orders[1:]
    assert "differs" in paper.guard(bad, PLAN, 10_000, 20, paper.PAPER_ORDERS_URL)
    assert "not Alpaca PAPER" in paper.guard(orders, PLAN, 10_000, 20, "https://api.alpaca.markets/v2/orders")
    assert "cap" in paper.guard(orders, PLAN, 3_000, 20, paper.PAPER_ORDERS_URL)                 # $700 > 20% of $3,000
    assert "cap" in paper.guard(orders, PLAN, 10_000, 20, paper.PAPER_ORDERS_URL, existing_notional=1_500)
    assert "one order" in paper.guard(orders, PLAN, 10_000, 20, paper.PAPER_ORDERS_URL, open_same_side=True)
    more = [dict(orders[0], qty="9")]
    assert "validated" in paper.guard(more, PLAN, 10_000, 20, paper.PAPER_ORDERS_URL)


def test_journal_writes_one_line_per_run(tmp_path):
    r = {"generated": "2026-11-26 10:00 UTC", "symbol": "TEST", "final": "GO", "judge": verdict(), "rules": {"verdict": "GO"},
         "laws": {"verdict": "GO", "results": [], "numbers": {"ev_r": 0.4}}, "order": {"qty": 3}}
    laws.journal(tmp_path / "journal.csv", r)
    laws.journal(tmp_path / "journal.csv", r)
    lines = (tmp_path / "journal.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3 and lines[0].startswith("time_utc") and "0.400" in lines[1]
    assert score.calls(tmp_path / "journal.csv")[0]["p"] == 0.58              # the score command reads what the journal writes
