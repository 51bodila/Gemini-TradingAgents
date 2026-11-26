"""Trading laws, offline: each law can block or shrink a trade, none can loosen one."""
from datetime import date

from gemini_tradingagents import desk, laws

TODAY = date(2026, 11, 26)
M = {"atr14": 2.0, "last_close": 100.0, "date": "2026-11-25", "avg_volume_20d": 5_000_000}


def verdict(**kw):
    v = {"decision": "long", "entry": 100.0, "stop": 97.0, "target": 107.5, "p_win": 0.55,
         "thesis": "Pullback to SMA50 in an uptrend.", "edge": "Index rebalancing buyers arrive next week. Sellers are forced.",
         "other_side": "forced sellers from a fund redemption", "invalidation": "close below 96", "paid_risks": ["trend"], "unpaid_risks": []}
    v.update(kw)
    return desk.add_targets(v)


def run(v, m=M, capital=10_000, sym="TEST"):
    calc = desk.sizing(v, m, capital)
    return laws.check(v, calc, m, capital, sym, today=TODAY)


def status(results, law):
    return next(x["status"] for x in results if x["law"] == law)


def test_good_trade_passes_every_law():
    v, res, f, n = run(verdict())
    assert v == "GO" and f == 1.0, res
    assert n["ev_r"] > 0 and n["kelly"] > 0
    assert {x["law"] for x in res} == {k for k, _, _ in laws.LAWS}


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


def test_no_chasing():
    v, res, _, n = run(verdict(entry=103.0, stop=100.0, target=110.5))   # 1.5 ATR above the last close on a long
    assert v == "NO-GO" and status(res, "chase") == "fail" and n["entry_vs_last_atr"] > 1


def test_expected_value_must_be_positive_after_costs():
    v, res, _, n = run(verdict(p_win=0.30))
    assert v == "NO-GO" and status(res, "ev") == "fail" and n["ev_r"] < 0
    assert run(verdict(p_win=None))[0] == "NO-GO"                       # no probability: no EV, fail closed


def test_quarter_kelly_only_shrinks():
    v, res, f, n = run(verdict(p_win=0.452))   # barely positive EV: Kelly says risk under 1%
    assert status(res, "kelly") == "cut" and 0 < f < 1 and v == "GO SMALLER"
    assert n["kelly_risk_pct"] < 1.0


def test_unpaid_risk_halves_size():
    v, res, f, _ = run(verdict(unpaid_risks=["earnings in 3 days"]))
    assert v == "GO SMALLER" and status(res, "paid_risk") == "cut" and abs(f - 0.5) < 1e-9
    assert abs(run(verdict(unpaid_risks="earnings in 3 days"))[2] - 0.5) < 1e-9     # a plain string is one risk, not 18


def test_liquidity_cap():
    v, res, f, n = run(verdict(), {**M, "avg_volume_20d": 1_000})       # $100k a day traded, position ~$3.3k
    assert status(res, "liquidity") == "cut" and f < 0.5 and n["pct_of_adv"] > 1


def test_crypto_volume_is_already_in_dollars():
    assert laws.dollar_volume("BTC-USD", {"avg_volume_20d": 3e10, "last_close": 90_000}) == 3e10
    assert laws.dollar_volume("NVDA", {"avg_volume_20d": 2e8, "last_close": 150}) == 3e10


def test_tail_gap_through_stop():
    # stop only 0.5 ATR away: 1% risk buys a big position, a 2 ATR gap would lose ~5%
    v, res, f, n = run(verdict(entry=100.0, stop=99.0, target=102.5))
    assert status(res, "tail") == "cut" and n["gap_loss_pct"] > 3 and f < 1


def test_laws_never_loosen():
    assert laws.combine("GO SMALLER", "GO") == "GO SMALLER" and laws.combine("GO", "NO-GO") == "NO-GO"


def test_journal_writes_one_line_per_run(tmp_path):
    r = {"generated": "2026-11-26 10:00 UTC", "symbol": "TEST", "final": "GO", "judge": verdict(), "rules": {"verdict": "GO"},
         "laws": {"verdict": "GO", "results": [], "numbers": {"ev_r": 0.4}}, "order": {"qty": 3}}
    laws.journal(tmp_path / "journal.csv", r)
    laws.journal(tmp_path / "journal.csv", r)
    lines = (tmp_path / "journal.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3 and lines[0].startswith("time_utc") and "0.400" in lines[1]
