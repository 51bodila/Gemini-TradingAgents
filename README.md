# Gemini TradingAgents

Built on TauricResearch/TradingAgents, HKUDS/Vibe-Trading and google/adk-python. Not affiliated with Google or Tauric Research. The command-line tool is called `gemini-desk`.

A trading desk in one command. Gemini 4 Neon thinks up the trade, Hydrogen backtests it, Argon argues it like a
hedge fund committee, and Carbon decides: GO, GO SMALLER or NO-GO, with entry, stop, target and position size.
Built on three of the most-starred open-source trading projects and Google's own agent framework.

**Requirements: Python 3.11, 3.12 or 3.13, and one Gemini API key on a Google project with billing enabled.** Windows, macOS, Linux. Market data needs no extra keys.

Billing is required: Gemini 4 Argon, Neon and Carbon have no free tier, and Hydrogen's free tier (20 requests a day) is not enough for one report. See [Cost](#cost).

```
gemini-desk AAPL

 1. Neon     ─▶ the brain           thesis + test plan (TradingAgents, or Gemini directly)
 2. Hydrogen ─▶ Vibe-Trading        prices, fundamentals, news; backtests Neon's plan + walk-forward
 3. Argon    ─▶ committee           bull vs bear vs risk officer vs portfolio manager   (2 and 3 run at the same time)
 4. Carbon   ─▶ ADK judge           reads everything ─▶ GO / GO SMALLER / NO-GO + entry, stop, target
 5. Python   ─▶ hard risk rules     can only make the verdict stricter ─▶ position size ─▶ optional Alpaca PAPER order
```

## What it is built on

| Job | Project | Stars | License | Gemini 4 model |
|---|---|---|---|---|
| The brain: thesis and test plan | [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 123,757 | Apache-2.0 | `gemini-4-neon` |
| Data pack, backtests, walk-forward | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 38,915 | MIT | `gemini-4-hydrogen` |
| Investment committee (`investment_committee` preset) | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 38,915 | MIT | `gemini-4-argon` |
| Final judge | [google/adk-python](https://github.com/google/adk-python) | 22,355 | Apache-2.0 | `gemini-4-carbon` |

Optional plugin (`install.ps1 -WithHedgeFund` / `install.sh --with-hedge-fund`): [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (64,851 stars, MIT), an investor committee of Graham, Buffett, Munger and earnings drift on `gemini-4-argon`. It runs only when `FINANCIAL_DATASETS_API_KEY` is set (financialdatasets.ai, $20 one-time for 1,000 requests).

Stars from the GitHub API on 2026-11-25. gemini-desk installs these as separate tools and calls their command lines; it copies none of their code. This repo is MIT.

## Why each model got its job

| Model | Google's description | Price per 1M tokens (in / out) | Vals Finance Index |
|---|---|---|---|
| `gemini-4-hydrogen` | fast daily driver | $1.50 / $7.50 | #3 of 46 |
| `gemini-4-argon` | flagship reasoning model | $2 / $10 until Nov 30 2026, then $4 / $20 | #4 of 46 |
| `gemini-4-neon` | between Carbon and Hydrogen | $3 / $15 | #1 of 46 (68.31%) |
| `gemini-4-carbon` | built on Argon, strongest for tasks that test the limits | $2 / $10 until Nov 30 2026, then $4 / $20 | #2 of 46 |

Prices: aistudio.google.com/docs/pricing. Rankings: vals.ai model pages. Both read on 2026-11-25. Any job can move to another model in `.env` (`GD_MODEL_COLLECTOR`, `GD_MODEL_ANALYST`, `GD_MODEL_STRATEGIST`, `GD_MODEL_JUDGE`).

## Install

Python 3.11, 3.12 or 3.13.

```
# Windows (PowerShell)
.\install.ps1

# macOS / Linux
sh install.sh
```

The installer works like pipx: each tool gets its own environment, because their dependencies clash (ai-hedge-fund pins `langchain-core<0.4`, Vibe-Trading needs `>=1.0`). `.venv` holds gemini-desk and `google-adk 2.15.1`; `.tools/vibe` holds `vibe-trading-ai 0.1.19`; `.tools/aihf` holds `aihf 2.7.2` only with `-WithHedgeFund` / `--with-hedge-fund`; TradingAgents `1.0.1` comes from its official installer. gemini-desk runs each tool by full path and imports none of them. Put one key in `.env`:

```
GEMINI_API_KEY=...        # aistudio.google.com
```

TradingAgents publishes Linux and macOS builds. On Windows the installer puts it inside WSL. If WSL has no Linux distribution yet, the installer prints the one command to run (`wsl --install`, once, as administrator); until then the Neon research question goes straight to Gemini and the report labels it "TradingAgents not available".

Check the setup:

```
gemini-desk doctor        # which tools are installed, which keys are set (values never printed)
gemini-desk models        # which model does which job
```

## Use

```
gemini-desk AAPL                       # all stages, one Markdown report in reports/
gemini-desk AAPL --fast                # cheapest mode (see Cost)
gemini-desk AAPL --only brain,vibe     # pick stages (brain, vibe, committee, aihf); the judge always runs
gemini-desk --dry-run AAPL             # print every command that would run, call nothing
gemini-desk AAPL --paper               # print the Alpaca PAPER bracket order from the latest verdict
gemini-desk AAPL --paper --send        # send it to Alpaca PAPER (paper-api.alpaca.markets only)
gemini-desk audit strategy.py --report backtest.txt   # Neon lists bugs, Carbon confirms each one
```

Every run also saves the data pack (`reports/<TICKER>-<time>-datapack.json` and `.md`): Python price metrics from Yahoo Finance with their as-of date, plus Vibe-Trading's prices, fundamentals, news and backtest with sources. The committee, Neon and the judge all work from it.

The report has the final verdict, the hard-rule checks, the judge's reasons and the conflicts it found between the three systems, the position size computed in Python, the target position, every tool's command and output, and the cost of the direct Gemini calls.

## Cost

Rough cost of one report at Google's list prices, measured from Vibe-Trading's token logs (each of its model calls
carries 60-110K input tokens). Google bills cached input at a lower rate, so real bills are usually lower.

| Mode | What runs | Approx. list price per report |
|---|---|---|
| `--fast` | Neon plan, Vibe-Trading 4 steps, one Argon committee call, Carbon judge | under $0.50 |
| default | Neon plan, Vibe-Trading 10 steps, Vibe-Trading 4-agent committee, Carbon judge | about $1.50-2.50 |
| `--deep` | Vibe-Trading 30 steps on 2 years of data, plus the default | several dollars |

Every report ends with a per-stage token and price table. Set a budget alert on your Google Cloud project
(Billing > Budgets & alerts) before running it on a schedule.

## Hard rules

Checked in plain Python after the judge. The judge can be stricter, never looser; the final verdict is the stricter of the two.

| Rule | Default | `.env` |
|---|---|---|
| Max loss at stop per trade | 1% of capital | `GD_MAX_RISK_PCT` |
| Max position size | 20% of capital | `GD_MAX_POSITION_PCT` |
| Min reward:risk | 1.5 | `GD_MIN_REWARD_RISK` |
| Stop at least this many ATR(14) away | 0.5 | `GD_MIN_STOP_ATR` |
| Entry no further from last close | 3% | `GD_MAX_ENTRY_GAP_PCT` |
| Daily loss limit | 2% | `GD_MAX_DAILY_LOSS_PCT` |
| Kill switch | a file named `KILL` blocks every trade | `GD_KILL_SWITCH` |

## Data and keys

| Stage | With only a Gemini key | Optional key |
|---|---|---|
| Vibe-Trading (data pack, committee) | US stocks via yfinance and public APIs that need no key (Yahoo, Stooq, Sina, Eastmoney); crypto via OKX public API | Finnhub, Alpha Vantage, Tiingo, FMP, FRED |
| TradingAgents | works from the data pack passed in the question | `TAURIC_API_KEY` lets it fetch filings, statements and news itself (tauric.ai) |
| ai-hedge-fund plugin | off | `FINANCIAL_DATASETS_API_KEY` (financialdatasets.ai: $20 one-time for 1,000 requests, or $200/month) or an x402 wallet |
| Judge price metrics | Yahoo Finance chart data, computed in Python | none |

Yahoo Finance data is for personal use. gemini-desk fetches data at run time and never stores or redistributes it (`reports/` and caches are git-ignored).

## Paper trading

`--paper` turns the target position into an Alpaca bracket order: limit entry, take-profit, stop-loss, whole shares. It prints by default. `--send` posts it to `https://paper-api.alpaca.markets` with `ALPACA_KEY` / `ALPACA_SECRET` from an Alpaca paper account (no deposit needed). The code contains no live-trading endpoint. It refuses dry-run results and NO-GO verdicts. Stocks only.

## Credits

- [google/adk-recipes](https://github.com/google/adk-recipes) financial-advisor sample (Apache-2.0): the data → trading → execution → risk layout.
- [kweinmeister/agentic-trading](https://github.com/kweinmeister/agentic-trading) (Apache-2.0): a risk guard with hard rules that can veto the trader.
- `mandates/committee.yaml` follows the mandate format of ai-hedge-fund's `hedge_fund/fund/example.yaml` (MIT).

Research and paper trading only. Not financial advice.
