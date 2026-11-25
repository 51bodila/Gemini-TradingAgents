"""Free market data, no API keys. Every number in the report is computed here, never by a model.

Sources:
- Stocks/ETFs: Yahoo Finance chart endpoint (unofficial, public, may change or rate-limit).
- Crypto: Binance public spot klines via data-api.binance.vision (market data only, no key; symbols ending in USDT).
- US filings: SEC EDGAR XBRL company facts (needs SEC_USER_AGENT="name email" per SEC fair-access rules).
"""
import json
import math
import os
import statistics as st
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (gemini-desk research tool)"
LAST_NAME = {}  # symbol -> company name from the price source


def _get(url, ua=UA, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def is_crypto(symbol):
    return symbol.upper().endswith("USDT")


def daily_bars(symbol, days=400):
    """Return list of (date, open, high, low, close, volume), oldest first."""
    s = symbol.upper()
    if is_crypto(s):
        try:
            raw = _get(f"https://data-api.binance.vision/api/v3/klines?symbol={s}&interval=1d&limit={min(days, 1000)}")
        except urllib.error.HTTPError as e:
            if e.code == 451:
                raise SystemExit("Binance returned HTTP 451 (blocked in your region). Try a VPN-free region or another data source.")
            raise
        LAST_NAME[s] = s[:-4]
        return [(datetime.fromtimestamp(k[0] / 1000, timezone.utc).date().isoformat(), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in raw]
    rng = "2y" if days > 260 else "1y"
    raw = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(s)}?range={rng}&interval=1d")
    res = raw["chart"]["result"][0]
    LAST_NAME[s] = res["meta"].get("longName") or res["meta"].get("shortName") or s
    q = res["indicators"]["quote"][0]
    out = []
    for i, ts in enumerate(res["timestamp"]):
        vals = [q[k][i] for k in ("open", "high", "low", "close", "volume")]
        if None in vals:
            continue
        out.append((datetime.fromtimestamp(ts, timezone.utc).date().isoformat(), *map(float, vals)))
    return out[-days:]


def _sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else float("nan")


def _rsi(closes, n=14):
    if len(closes) <= n:
        return float("nan")
    gains, losses = [], []
    for a, b in zip(closes[-n - 1:-1], closes[-n:]):
        d = b - a
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag, al = sum(gains) / n, sum(losses) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def _atr(bars, n=14):
    trs = []
    for (_, _, h, l, c, _), (_, _, _, _, pc, _) in zip(bars[-n:], bars[-n - 1:-1]):
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else float("nan")


def metrics(bars):
    """Technical and risk numbers computed in Python."""
    closes = [b[4] for b in bars]
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    ann = 365 if is_crypto_bars(bars) else 252
    peak, mdd = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        mdd = min(mdd, c / peak - 1)
    last = closes[-1]

    def chg(n):
        return last / closes[-n - 1] - 1 if len(closes) > n else float("nan")

    vol20 = st.pstdev(rets[-20:]) * math.sqrt(ann) if len(rets) >= 20 else float("nan")
    vol250 = st.pstdev(rets[-250:]) * math.sqrt(ann) if len(rets) >= 60 else float("nan")
    hi52, lo52 = max(b[2] for b in bars[-252:]), min(b[3] for b in bars[-252:])
    return {
        "last_close": last, "date": bars[-1][0], "bars": len(bars),
        "chg_1d": chg(1), "chg_5d": chg(5), "chg_20d": chg(20), "chg_60d": chg(60), "chg_250d": chg(250),
        "sma20": _sma(closes, 20), "sma50": _sma(closes, 50), "sma200": _sma(closes, 200),
        "rsi14": _rsi(closes), "atr14": _atr(bars), "vol20_ann": vol20, "vol250_ann": vol250,
        "max_drawdown": mdd, "high_52w": hi52, "low_52w": lo52,
        "avg_volume_20d": sum(b[5] for b in bars[-20:]) / min(20, len(bars)),
    }


def is_crypto_bars(bars):
    # crypto trades on weekends: count weekend dates in the last 30 bars
    from datetime import date
    return sum(date.fromisoformat(b[0]).weekday() >= 5 for b in bars[-30:]) > 3


def fmt_metrics(m):
    pct = lambda v: "n/a" if v != v else f"{v * 100:+.2f}%"
    ab = lambda v: "n/a" if v != v else f"{v * 100:.2f}%"
    num = lambda v: "n/a" if v != v else f"{v:,.2f}"
    return "\n".join([
        f"Last close: {num(m['last_close'])} on {m['date']} ({m['bars']} daily bars)",
        f"Change: 1d {pct(m['chg_1d'])}, 5d {pct(m['chg_5d'])}, 20d {pct(m['chg_20d'])}, 60d {pct(m['chg_60d'])}, 250d {pct(m['chg_250d'])}",
        f"SMA20 {num(m['sma20'])}, SMA50 {num(m['sma50'])}, SMA200 {num(m['sma200'])}",
        f"RSI14 {num(m['rsi14'])}, ATR14 {num(m['atr14'])}",
        f"Volatility (annualized): 20d {ab(m['vol20_ann'])}, 1y {ab(m['vol250_ann'])}",
        f"Max drawdown in window: {pct(m['max_drawdown'])}; 52w high {num(m['high_52w'])}, low {num(m['low_52w'])}",
        f"Avg volume 20d: {num(m['avg_volume_20d'])}",
    ])


FACT_KEYS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "NetIncomeLoss", "OperatingIncomeLoss",
             "EarningsPerShareDiluted", "CashAndCashEquivalentsAtCarryingValue", "LongTermDebt", "StockholdersEquity",
             "NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment"]


def sec_facts(ticker):
    """Last 8 reported values of key US-GAAP facts from SEC EDGAR. Returns text, or a note why it is missing."""
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        return "SEC filings skipped: set SEC_USER_AGENT=\"Your Name your@email\" in .env (SEC requires it)."
    if is_crypto(ticker):
        return "No SEC filings for crypto."
    tickers = _get("https://www.sec.gov/files/company_tickers.json", ua=ua)
    time.sleep(0.2)  # SEC fair access: stay well under 10 requests per second
    cik = next((v["cik_str"] for v in tickers.values() if v["ticker"].upper() == ticker.upper()), None)
    if not cik:
        return f"SEC: no CIK found for {ticker} (not a US filer, or an ETF)."
    facts = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json", ua=ua)
    gaap = facts.get("facts", {}).get("us-gaap", {})
    lines = [f"SEC EDGAR company facts for {facts.get('entityName', ticker)} (CIK {cik}):"]
    for k in FACT_KEYS:
        if k not in gaap:
            continue
        units = gaap[k]["units"]
        unit = "USD" if "USD" in units else next(iter(units))
        rows = [r for r in units[unit] if r.get("form") in ("10-K", "10-Q") and r.get("fp")]
        seen, last = set(), []
        for r in sorted(rows, key=lambda r: r["end"], reverse=True):
            tag = (r["end"], r["fp"])
            if tag in seen:
                continue
            seen.add(tag)
            last.append(f"{r['end']} {r['fp']} {r['val']:,}")
            if len(last) == 8:
                break
        lines.append(f"- {k} ({unit}): " + "; ".join(last))
    return "\n".join(lines)
