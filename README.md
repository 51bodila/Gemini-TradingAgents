# Gemini TradingAgents

**Run 4 Gemini 4 models as one hedge fund desk.**

Built on TauricResearch/TradingAgents, HKUDS/Vibe-Trading and google/adk-python. Not affiliated with Google or Tauric Research. The command-line tool is called `gemini-tradingagents`.

One command, four Gemini 4 models. Gemini 4 Neon thinks up the trade, Hydrogen backtests it, Argon argues it like a
hedge fund committee, and Carbon decides: GO, GO SMALLER or NO-GO, with entry, stop, two targets and position size.
Built on three of the most-starred open-source trading projects and Google's own agent framework.

**Requirements: Python 3.11, 3.12 or 3.13, and one Gemini API key on a Google project with billing enabled.** Windows, macOS, Linux. Market data needs no extra keys.

Billing is required: Gemini 4 Argon, Neon and Carbon have no free tier, and Hydrogen's free tier (20 requests a day) is not enough for one report. See [Cost](#cost).

```
gemini-tradingagents AAPL

 1. Neon     ─▶ the brain           thesis + test plan (TradingAgents, or Gemini directly)
 2. Hydrogen ─▶ Vibe-Trading        prices, fundamentals, news; backtests Neon's plan + walk-forward
 3. Argon    ─▶ committee           bull vs bear vs risk officer vs portfolio manager   (2 and 3 run at the same time)
 4. Carbon   ─▶ ADK judge           reads everything ─▶ GO / GO SMALLER / NO-GO + entry, stop, Target 1, Target 2
 5. Python   ─▶ hard risk rules + Jane Street rules   only stricter ─▶ position size ─▶ optional Alpaca PAPER order
```

## What it is built on

| Job | Project | Stars | License | Gemini 4 model |
|---|---|---|---|---|
| The brain: thesis and test plan | [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 123,757 | Apache-2.0 | `gemini-4-neon` |
| Data pack, backtests, walk-forward | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 38,915 | MIT | `gemini-4-hydrogen` |
| Investment committee (`investment_committee` preset) | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 38,915 | MIT | `gemini-4-argon` |
| Final judge | [google/adk-python](https://github.com/google/adk-python) | 22,355 | Apache-2.0 | `gemini-4-carbon` |

Optional plugin (`install.ps1 -WithHedgeFund` / `install.sh --with-hedge-fund`): [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (64,851 stars, MIT), an investor committee of Graham, Buffett, Munger and earnings drift on `gemini-4-argon`. It runs only when `FINANCIAL_DATASETS_API_KEY` is set (financialdatasets.ai, $20 one-time for 1,000 requests).

Stars from the GitHub API on 2026-11-25. gemini-tradingagents installs these as separate tools and calls their command lines; it copies none of their code. This repo is MIT.

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

The installer works like pipx: each tool gets its own environment, because their dependencies clash (ai-hedge-fund pins `langchain-core<0.4`, Vibe-Trading needs `>=1.0`). `.venv` holds gemini-tradingagents and `google-adk 2.15.1`; `.tools/vibe` holds `vibe-trading-ai 0.1.19`; `.tools/aihf` holds `aihf 2.7.2` only with `-WithHedgeFund` / `--with-hedge-fund`; TradingAgents `1.0.1` comes from its official installer. gemini-tradingagents runs each tool by full path and imports none of them. Put one key in `.env`:

```
GEMINI_API_KEY=...        # aistudio.google.com
```

TradingAgents publishes Linux and macOS builds. On Windows the installer puts it inside WSL. If WSL has no Linux distribution yet, the installer prints the one command to run (`wsl --install`, once, as administrator); until then the Neon research question goes straight to Gemini and the report labels it "TradingAgents not available".

Check the setup:

```
gemini-tradingagents doctor        # which tools are installed, which keys are set (values never printed)
gemini-tradingagents models        # which model does which job
```

## Use

```
gemini-tradingagents AAPL                       # all stages, one Markdown report in reports/
gemini-tradingagents AAPL --fast                # cheapest mode (see Cost)
gemini-tradingagents AAPL --only brain,vibe     # pick stages (brain, vibe, committee, aihf); the judge always runs
gemini-tradingagents --dry-run AAPL             # print every command that would run, call nothing
gemini-tradingagents AAPL --paper               # print the Alpaca PAPER bracket order from the latest verdict
gemini-tradingagents AAPL --paper --send        # send it to Alpaca PAPER (paper-api.alpaca.markets only)
gemini-tradingagents audit strategy.py --report backtest.txt   # Neon lists bugs, Carbon confirms each one
```

Every run also saves the data pack (`reports/<TICKER>-<time>-datapack.json` and `.md`): Python price metrics from Yahoo Finance with their as-of date, plus Vibe-Trading's prices, fundamentals, news and backtest with sources. The committee, Neon and the judge all work from it.

The report has the final verdict, the hard-rule checks, the judge's reasons and the conflicts it found between the three systems, the position size computed in Python, the target position with Target 1 (1R) and Target 2 (the judge's target, or 2.5R if it gave none), every tool's command and output, and the cost of the direct Gemini calls.

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

## Jane Street rules inside

Inspired by Jane Street's public materials. Not affiliated with or endorsed by Jane Street. Jane Street offers no retail apps or accounts ([fraud and impersonation warnings](https://www.janestreet.com/fraud-and-impersonation-warnings/)).

Jane Street publishes no trading rulebook. The rules below come from its public materials (the [Probability & Markets guide](https://www.janestreet.com/static/pdfs/trading-interview.pdf), the podcast *Signals and Threads*, its tech blog), from *The Laws of Trading* (Wiley, 2019) by Agustin Lebron, a former Jane Street trader (quoted via [this review](https://www.astralcodexten.com/p/your-book-review-the-laws-of-trading)), and from standard math. Each one runs in plain Python after the judge. Like the hard rules, they can only block a trade or shrink it, never loosen it, and a missing answer counts as NO-GO. Several "half size" rules do not compound: the size is halved once.

| # | Rule | Source (exact quote, or "standard math") | What the code does |
|---|---|---|---|
| 1 | Fail closed on bad data | Jane Street, [Signals and Threads](https://signalsandthreads.com/finding-signal-in-the-noise/): "being sloppy with data science is fatal" | NO-GO if entry, stop, targets or ATR14 are missing, or the last bar is over 4 days old |
| 2 | Know why you trade | Lebron (ex-Jane Street): "Know why you are doing a trade before you trade." | NO-GO without a thesis and an invalidation |
| 3 | Explain your edge | Lebron: "If you can't explain your edge in five minutes, you don't have a very good one." | NO-GO without an edge, or with more than 5 sentences |
| 4 | Who is on the other side? | Jane Street [guide](https://www.janestreet.com/static/pdfs/trading-interview.pdf): "Adverse selection is the idea that the trades you get to do are worse than they would appear" | NO-GO unless the judge names the counterparty and why they trade with you |
| 5 | Two independent yeses | repo idea (pre-trade checks) | NO-GO if Neon's plan or the Argon committee points the other way; half size if the committee is neutral, split, missing, or has no real bear case (rubber stamp) |
| 6 | Don't chase | Jane Street guide (adverse selection) | NO-GO if the entry is more than 1 ATR beyond the last close in the trade direction |
| 7 | Cool off | repo idea (kill hierarchy) | NO-GO for 24 h after 3 losses in a row in the journal |
| 8 | Keep score | standard math (Brier score, calibration) | after 20 resolved calls, the judge's probability is scaled by hit rate / predicted rate (only ever down) |
| 9 | Positive expected value after costs | Jane Street guide: "If you know the expected value of something, you should be happy to buy for less or sell for more." Lebron: "If you think your costs are negligible relative to your edge, you're wrong about at least one of them." | EV in R from the judge's probability minus 0.05, half out at Target 1 and half at Target 2, minus fees (10 bps) and slippage (0.1 ATR); EV <= 0 is NO-GO |
| 10 | Never pay above value | Jane Street guide (expected value above); idea from RasmusCodes/figgie-bot | NO-GO if a long's entry is above p x Target 1 + (1 - p) x stop (mirror for shorts) |
| 11 | Size by edge | standard sizing math (Kelly/Thorp) | quarter Kelly; if it allows less than the 1% rule, the size is cut; Kelly <= 0 is NO-GO |
| 12 | Take only paid risks | Lebron: "Take only the risks you're being paid to take. Hedge the others." | any unpaid risk the judge lists (earnings, macro, unlock) halves the size |
| 13 | The model may remember the test period | Jane Street blog, [Mitigating memorization in LLMs](https://blog.janestreet.com/mitigating-memorization-in-llms/): "A model may perform well on a historical benchmark by consulting its memorized knowledge of past outcomes" | half size unless out-of-sample data runs past `GD_JS_MODEL_CUTOFF` (default 2026-01-01) |
| 14 | Edges decay | standard practice | half size if the backtest's recent half earned under 50% of the older half, lost money, or was not reported |
| 15 | Purged walk-forward | Jane Street blog, [Flex Model](https://blog.janestreet.com/flex-model-an-event-driven-feature-engineering-system/): "The same feature code ran live and in historical mode"; embargo idea from Kaggle Jane Street solutions | Hydrogen is asked for an embargo of max(lookback, holding period) bars between train and test; half size if it is shorter or not reported |
| 16 | Use liquid instruments | Lebron: "Put on a risk using the most liquid instrument for that risk." | position <= 1% of 20-day average dollar volume |
| 17 | Survive the unseen | Lebron: "Just because something has never happened doesn't mean it can't." | a 2 ATR gap past the stop must cost <= 3% of capital, otherwise the size is cut |
| 18 | The AI never types the order | repo ideas (pre-trade checks; one order per symbol and side) | `--paper` refuses if any order field differs from the Python-validated plan, the endpoint is not paper-api.alpaca.markets, existing position + open orders + the new order exceed the 20% cap, or an open order on the same symbol and side exists |
| 19 | Limits are frozen | repo idea (an agent may never raise limits) | limits come only from `.env`; any extra field in the judge's output is dropped, and the prompt says it may not propose changing limits or disabling the kill switch |

Every rule, its result and its numbers go into the report. Each real run appends one line to `reports/journal.csv`. `gemini-tradingagents score` resolves past calls against later daily bars (Target 1 before the stop is a win, the stop first is a loss, both in one bar is a loss) and prints the hit rate, mean predicted probability, Brier score and a calibration table. Thresholds are in `.env`: `GD_FEE_BPS`, `GD_SLIPPAGE_ATR`, `GD_P_MARGIN`, `GD_KELLY_FRACTION`, `GD_MAX_ENTRY_ATR`, `GD_MAX_ADV_PCT`, `GD_GAP_ATR`, `GD_MAX_GAP_LOSS_PCT`, `GD_MAX_DATA_AGE_DAYS`, `GD_UNPAID_RISK_CUT`, `GD_HALF_CUT`, `GD_JS_MODEL_CUTOFF`, `GD_DECAY_RATIO`, `GD_MIN_RESOLVED`, `GD_COOLOFF_LOSSES`, `GD_COOLOFF_HOURS`.

Ideas from (no code copied): [voyager67/JaneStreet-Agentic-Skills](https://github.com/voyager67/JaneStreet-Agentic-Skills) (Apache-2.0), [EnriqueKhai/JaneStreetETC22](https://github.com/EnriqueKhai/JaneStreetETC22) (BSD-3-Clause), [RasmusCodes/figgie-bot](https://github.com/RasmusCodes/figgie-bot) (MIT), [scaomath/kaggle-jane-street](https://github.com/scaomath/kaggle-jane-street) and [evgeniavolkova/kagglejanestreet](https://github.com/evgeniavolkova/kagglejanestreet) (no license; ideas only).

## Data and keys

| Stage | With only a Gemini key | Optional key |
|---|---|---|
| Vibe-Trading (data pack, committee) | US stocks via yfinance and public APIs that need no key (Yahoo, Stooq, Sina, Eastmoney); crypto via OKX public API | Finnhub, Alpha Vantage, Tiingo, FMP, FRED |
| TradingAgents | works from the data pack passed in the question | `TAURIC_API_KEY` lets it fetch filings, statements and news itself (tauric.ai) |
| ai-hedge-fund plugin | off | `FINANCIAL_DATASETS_API_KEY` (financialdatasets.ai: $20 one-time for 1,000 requests, or $200/month) or an x402 wallet |
| Judge price metrics | Yahoo Finance chart data, computed in Python | none |

Yahoo Finance data is for personal use. gemini-tradingagents fetches data at run time and never stores or redistributes it (`reports/` and caches are git-ignored).

## See it on TradingView

Every run also writes `reports/<TICKER>_<time>.pine`, a Pine Script v6 indicator with that run's entry, stop, Target 1, Target 2, verdict and panel filled in:

1. Open TradingView and the Pine Editor (bottom panel).
2. Paste the whole `reports/<TICKER>_<time>.pine` file.
3. Click **Add to chart**.

It draws the levels with price tags, a RISK 1R box and a REWARD box from the signal bar, a LONG / SHORT label and a verdict panel. `gemini_tradingagents/pine_template.pine` is the same script with blank levels: paste it and type your own levels in the indicator settings.

## Paper trading

`--paper` turns the target position into Alpaca bracket orders: limit entry, stop-loss, whole shares; half the shares take profit at Target 1, the rest at Target 2 (one share: a single bracket to Target 2). It prints by default. `--send` posts it to `https://paper-api.alpaca.markets` with `ALPACA_KEY` / `ALPACA_SECRET` from an Alpaca paper account (no deposit needed). The code contains no live-trading endpoint. It refuses dry-run results and NO-GO verdicts. Stocks only.

## Credits

- [google/adk-recipes](https://github.com/google/adk-recipes) financial-advisor sample (Apache-2.0): the data → trading → execution → risk layout.
- [kweinmeister/agentic-trading](https://github.com/kweinmeister/agentic-trading) (Apache-2.0): a risk guard with hard rules that can veto the trader.
- `mandates/committee.yaml` follows the mandate format of ai-hedge-fund's `hedge_fund/fund/example.yaml` (MIT).

Research and paper trading only. Not financial advice.
