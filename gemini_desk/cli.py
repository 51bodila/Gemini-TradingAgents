"""gemini-desk command line.

  gemini-desk AAPL                     run all 4 stages, write one report
  gemini-desk AAPL --only vibe,ta      run some stages (vibe, aihf, ta); the Carbon judge always runs
  gemini-desk AAPL --paper             print the Alpaca PAPER order from the latest AAPL verdict
  gemini-desk AAPL --paper --send      send it to Alpaca PAPER (paper-api only)
  gemini-desk audit strategy.py --report backtest.txt
  gemini-desk doctor                   what is installed, which keys are set
  gemini-desk models                   which model does which job
  gemini-desk --dry-run AAPL           show every command, call nothing
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .llm import Gemini
from .roles import PRICES, ROLES, model_for

JOBS = {"collector": "Vibe-Trading: data, backtest, walk-forward", "analyst": "ai-hedge-fund: investor committee",
        "strategist": "TradingAgents: deep research with sources", "judge": "ADK judge: final verdict + target position"}


def load_env(path=".env"):
    for p in (Path(path), Path(__file__).resolve().parent.parent / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if v.strip():
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return


def _ver(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=60, env={**os.environ, "WSL_UTF8": "1"})
        raw = p.stdout or p.stderr
        txt = raw.decode("utf-16-le" if b"\x00" in raw else "utf-8", errors="replace").strip()  # wsl.exe may answer in UTF-16
        return txt.splitlines()[0][:90] if txt else f"exit {p.returncode}"
    except (FileNotFoundError, subprocess.TimeoutExpired, IndexError) as e:
        return f"missing ({type(e).__name__})"


def doctor():
    print("Tools:")
    from .stages import aihf_exe, vibe_exe
    for label, exe in (("vibe-trading", vibe_exe()), ("aihf (optional)", aihf_exe())):
        print(f"  {label:15s} {_ver([exe, '--version'])}  [{exe}]")
    if shutil.which("tradingagents") or platform.system() != "Windows":
        print(f"  tradingagents  {_ver(['tradingagents', '--version'])}")
    else:
        print(f"  tradingagents  (WSL) {_ver(['wsl', '-e', 'bash', '-lc', '~/.local/bin/tradingagents --version'])}")
    try:
        import google.adk
        print(f"  google-adk     {getattr(google.adk, '__version__', 'installed')}")
    except ImportError:
        print("  google-adk     missing (judge falls back to plain HTTPS)")
    print("Keys (set or not, values never printed):")
    for k in ["GEMINI_API_KEY", "FINANCIAL_DATASETS_API_KEY", "X402_WALLET_PRIVATE_KEY", "TAURIC_API_KEY", "ALPACA_KEY", "ALPACA_SECRET", "SEC_USER_AGENT"]:
        print(f"  {k:28s} {'set' if os.environ.get(k) else '-'}")


def main(argv=None):
    load_env()
    from .certs import env as ca_env
    for k, v in ca_env().items():  # same CA fix for google-adk / httpx in this process
        os.environ.setdefault(k, v)
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="gemini-desk", description="Three proven trading repos, four Gemini 4 models, one verdict.")
    ap.add_argument("--dry-run", action="store_true", help="show every command, call nothing (no key needed)")
    ap.add_argument("--out", default="reports")
    cmds = {"audit", "doctor", "models"}
    first = next((a for a in argv if not a.startswith("-")), None)
    if first and first not in cmds:
        ap.add_argument("symbol")
        ap.add_argument("--only", help="comma list of stages: vibe, committee, ta, aihf")
        ap.add_argument("--capital", type=float, default=10_000)
        ap.add_argument("--deep", action="store_true", help="heavier Vibe-Trading run (2 years, 30 steps): slower and costlier")
        ap.add_argument("--fast", action="store_true", help="cheapest: Vibe-Trading 4 steps + one Argon committee call")
        ap.add_argument("--paper", action="store_true", help="build the Alpaca PAPER order from the latest verdict")
        ap.add_argument("--send", action="store_true", help="with --paper: send it (paper-api.alpaca.markets only)")
        args = ap.parse_args(argv)
        out = Path(args.out)
        out.mkdir(exist_ok=True)
        if args.paper:
            from .paper import paper
            return paper(args.symbol, out, send=args.send)
        from .desk import report_md, run
        llm = Gemini(dry_run=args.dry_run)
        r = run(llm, args.symbol, out, args.capital, args.dry_run, args.only.split(",") if args.only else None, deep=args.deep, fast=args.fast)
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        path = out / f"{r['symbol']}-{stamp}{'-dryrun' if args.dry_run else ''}.md"
        path.write_text(report_md(r, llm.usage.table()), encoding="utf-8")
        (out / f"{r['symbol']}-latest.order.json").write_text(json.dumps(
            {"order": r["order"], "final": r["final"], "generated": r["generated"], "dry_run": args.dry_run}, indent=1))
        for s in r["stages"]:
            print(f"{s['stage']:14s} {s.get('model', ''):18s} {s['status']}" + (f"  $ {s['command']}" if args.dry_run else ""))
            if s["status"] in ("needs billing", "failed") and s.get("stderr"):
                print("               " + s["stderr"].splitlines()[0][:200])
        print(f"Judge          {model_for('judge'):18s} {r['judge_engine']}")
        print(f"Verdict: {r['final']}\nReport: {path}")
        return 0
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="second opinion on a strategy's code and backtest report (Neon finds, Carbon confirms)")
    a.add_argument("code", nargs="+")
    a.add_argument("--report")
    sub.add_parser("doctor")
    sub.add_parser("models")
    args = ap.parse_args(argv)
    if args.cmd == "doctor":
        return doctor()
    if args.cmd == "models":
        for role, m in ((r, model_for(r)) for r in ROLES):
            print(f"{m:20s} ${PRICES[m][0]}/{PRICES[m][1]} per 1M  {JOBS[role]}")
        return 0
    from .audit import audit, audit_md
    llm = Gemini(dry_run=args.dry_run)
    findings, v = audit(llm, args.code, args.report)
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    path = out / f"audit-{datetime.now().strftime('%Y%m%d-%H%M')}{'-dryrun' if args.dry_run else ''}.md"
    path.write_text(audit_md(findings, v, llm.usage.table()), encoding="utf-8")
    print(f"Verdict: {v.get('verdict', 'n/a')}\nReport: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
