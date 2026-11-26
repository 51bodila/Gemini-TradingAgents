"""TradingView script for each run: a Pine Script v6 indicator with the run's levels filled in as input defaults.

Paste it into TradingView's Pine Editor and click "Add to chart". It draws entry, stop, Target 1 and Target 2 with price
tags, a RISK 1R box and a REWARD box from the signal bar, a LONG/SHORT label and a panel with the verdict.
gemini_tradingagents/pine_template.pine is the same script with neutral defaults, for typing levels in by hand.
"""
import re
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE = r'''//@version=6
// Gemini TradingAgents: levels and verdict from one run of gemini-tradingagents.
// {{NOTE}}
// Research and paper trading only. Not financial advice.
indicator("Gemini TradingAgents", overlay = true, max_boxes_count = 10, max_lines_count = 20, max_labels_count = 20)

// ---- values from the run (editable in the indicator settings)
string iSymbol    = input.string("{{SYMBOL}}", "Symbol of the run")
string iSide      = input.string("{{SIDE}}", "Side", options = ["long", "short", "none"])
string iVerdict   = input.string("{{VERDICT}}", "Verdict", options = ["GO", "GO SMALLER", "NO-GO"])
float  iEntry     = input.float({{ENTRY}}, "Entry")
float  iStop      = input.float({{STOP}}, "Stop")
float  iT1        = input.float({{T1}}, "Target 1")
float  iT2        = input.float({{T2}}, "Target 2")
int    iSignal    = input.time(timestamp("UTC", {{Y}}, {{MO}}, {{D}}, {{H}}, {{MI}}), "Signal bar")
string iRegime    = input.string("{{REGIME}}", "Regime")
string iThesis    = input.string("{{THESIS}}", "Neon thesis")
string iBacktest  = input.string("{{BACKTEST}}", "Backtest")
string iCommittee = input.string("{{COMMITTEE}}", "Committee")
string iRules     = input.string("{{RULES}}", "Risk rules")
string iSize      = input.string("{{SIZE}}", "Size")
int    iBarsRight = input.int(20, "Box length (bars to the right)", minval = 1)

// ---- colours
color cGreen = #089981
color cRed   = #f23645
color cGold  = #f6a623
color cText  = #e8eaf0
color cMuted = #aab0bd
color cPanel = #101420

bool  isLong   = iSide == "long"
bool  hasTrade = iSide != "none" and iEntry > 0 and iStop > 0 and iT1 > 0 and iT2 > 0
color cVerdict = iVerdict == "NO-GO" ? #787b86 : isLong ? cGreen : cRed

var table panel = table.new(position.top_right, 2, 12, bgcolor = cPanel, frame_color = #3a4256, frame_width = 1, border_color = #1f2433, border_width = 1)

levelLine(float price, color col, int x1, int x2, string txt, color txtCol) =>
    line.new(x1, price, x2, price, xloc = xloc.bar_time, color = col, width = 2)
    label.new(x2, price, txt + " " + str.tostring(price, format.mintick), xloc = xloc.bar_time, style = label.style_label_left, color = col, textcolor = txtCol, size = size.small)

row(int r, string k, string v, color vCol) =>
    table.cell(panel, 0, r, k, text_color = cMuted, text_halign = text.align_left, text_size = size.small)
    table.cell(panel, 1, r, v, text_color = vCol, text_halign = text.align_right, text_size = size.small)

if barstate.islast
    if hasTrade
        int xRight = time + iBarsRight * timeframe.in_seconds() * 1000
        box.new(iSignal, math.max(iEntry, iStop), xRight, math.min(iEntry, iStop), xloc = xloc.bar_time, border_color = cRed, bgcolor = color.new(cRed, 75), text = "RISK 1R", text_color = color.white, text_size = size.small, text_halign = text.align_right, text_valign = isLong ? text.align_bottom : text.align_top)
        box.new(iSignal, math.max(iEntry, iT2), xRight, math.min(iEntry, iT2), xloc = xloc.bar_time, border_color = cGreen, bgcolor = color.new(cGreen, 75), text = "REWARD", text_color = color.white, text_size = size.small, text_halign = text.align_right, text_valign = isLong ? text.align_top : text.align_bottom)
        levelLine(iEntry, cGold, iSignal, xRight, "ENTRY", #1a1205)
        levelLine(iStop, cRed, iSignal, xRight, "STOP", color.white)
        levelLine(iT1, #22e39a, iSignal, xRight, "T1", #06281c)
        levelLine(iT2, cGreen, iSignal, xRight, "T2", color.white)
        label.new(iSignal, iEntry, isLong ? "▲ LONG" : "▼ SHORT", xloc = xloc.bar_time, style = isLong ? label.style_label_up : label.style_label_down, color = isLong ? cGreen : cRed, textcolor = color.white, size = size.normal)
    table.cell(panel, 0, 0, "GEMINI TRADINGAGENTS", text_color = #7cc4ff, text_halign = text.align_left, text_size = size.small)
    table.cell(panel, 1, 0, iSymbol, text_color = cMuted, text_halign = text.align_right, text_size = size.small)
    table.cell(panel, 0, 1, (iVerdict == "NO-GO" ? "" : isLong ? "▲ " : "▼ ") + iVerdict, bgcolor = cVerdict, text_color = color.white, text_size = size.large)
    table.merge_cells(panel, 0, 1, 1, 1)
    row(2, "Regime", iRegime, cText)
    row(3, "Neon thesis", iThesis, cText)
    row(4, "Backtest", iBacktest, cText)
    row(5, "Committee", iCommittee, cText)
    row(6, "Entry", hasTrade ? str.tostring(iEntry, format.mintick) : "none", cText)
    row(7, "Stop", hasTrade ? str.tostring(iStop, format.mintick) : "none", cRed)
    row(8, "Targets", hasTrade ? str.tostring(iT1, format.mintick) + " / " + str.tostring(iT2, format.mintick) : "none", cGreen)
    row(9, "Risk rules", iRules, cGold)
    row(10, "Size", iSize, cText)
    table.cell(panel, 0, 11, "Example run · not financial advice", text_color = #6f7688, text_size = size.tiny)
    table.merge_cells(panel, 0, 11, 1, 11)
'''


def _s(x, n=70):
    """A safe one-line Pine string literal body."""
    x = re.sub(r"\s+", " ", str(x or "")).replace("\\", "/").replace('"', "'").strip()
    return (x[: n - 1] + "…") if len(x) > n else (x or "n/a")


def _num(x):
    try:
        t = f"{float(x):.8f}".rstrip("0")
        return t + "0" if t.endswith(".") else t
    except (TypeError, ValueError):
        return "0.0"


def render(v, when=None):
    when = when or datetime.now(timezone.utc)
    out = TEMPLATE
    for k, val in {"NOTE": v.get("note", ""), "SYMBOL": _s(v.get("symbol")), "SIDE": v.get("side", "none"), "VERDICT": v.get("verdict", "NO-GO"),
                   "ENTRY": _num(v.get("entry")), "STOP": _num(v.get("stop")), "T1": _num(v.get("t1")), "T2": _num(v.get("t2")),
                   "Y": when.year, "MO": when.month, "D": when.day, "H": when.hour, "MI": when.minute,
                   "REGIME": _s(v.get("regime")), "THESIS": _s(v.get("thesis")), "BACKTEST": _s(v.get("backtest")),
                   "COMMITTEE": _s(v.get("committee")), "RULES": _s(v.get("rules")), "SIZE": _s(v.get("size"))}.items():
        out = out.replace("{{" + k + "}}", str(val))
    return out


def generic():
    """The hand-edit template gemini_tradingagents/pine_template.pine: neutral defaults, every value is an input."""
    return render({"note": "Template: type your own levels in the indicator settings.", "symbol": "TICKER", "side": "long", "verdict": "GO",
                   "entry": 100, "stop": 95, "t1": 105, "t2": 112.5, "regime": "n/a", "thesis": "n/a", "backtest": "n/a",
                   "committee": "n/a", "rules": "1% risk, 20% cap", "size": "n/a"}, datetime(2026, 1, 1, tzinfo=timezone.utc))


def _line(text, prefix):
    for ln in (text or "").splitlines():
        if ln.strip().startswith(prefix):
            return ln.split(":", 1)[1].strip()
    return ""


def from_run(r):
    j, o, rl = r.get("judge") or {}, r.get("order"), r.get("rules") or {}
    side = j.get("decision") if j.get("decision") in ("long", "short") and j.get("target_1") is not None else "none"
    st = {s.get("stage"): s for s in r.get("stages", [])}
    vibe = next((s for k, s in st.items() if "Vibe" in str(k)), None)
    com = next((s for k, s in st.items() if "ommittee" in str(k)), None)
    factor = rl.get("size_factor", 1)
    unit = "shares" if not re.search(r"(-USD|USDT|USDC)$", r["symbol"]) else r["symbol"].split("-")[0]
    return {"note": f"Run {r.get('generated', '')}. Values below are this run's.", "symbol": r["symbol"], "side": side, "verdict": r.get("final", "NO-GO"),
            "entry": j.get("entry"), "stop": j.get("stop"), "t1": j.get("target_1"), "t2": j.get("target_2"),
            "regime": _line(r.get("plan_txt"), "Direction"), "thesis": _line(r.get("plan_txt"), "Thesis"),
            "backtest": f"Vibe-Trading: {vibe['status']}" if vibe else "not run", "committee": f"{com['stage']}: {com['status']}" if com else "not run",
            "rules": f"{rl.get('verdict', 'n/a')}" + (f", size cut to {factor:.0%}" if factor and factor < 1 else ""),
            "size": f"{o['qty']:g} {unit}" if o else "no position"}


def write(r, out_dir, stamp):
    path = Path(out_dir) / f"{re.sub(r'[^A-Za-z0-9.-]', '_', r['symbol'])}_{stamp}.pine"
    path.write_text(render(from_run(r)), encoding="utf-8")
    return path
