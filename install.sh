#!/usr/bin/env sh
# gemini-tradingagents installer for macOS / Linux. Like pipx: each tool in its own environment (their langchain pins clash).
#   .venv          gemini-tradingagents + google-adk
#   .tools/vibe    vibe-trading-ai 0.1.19
#   .tools/aihf    aihf 2.7.2 (optional: --with-hedge-fund)
#   ~/.local/bin   TradingAgents 1.0.1
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
step() { printf '\n%s\n' "$1"; }

step "[1/6] Python"
"$PY" -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,14), "need Python 3.11-3.13"'

step "[2/6] .venv: gemini-tradingagents + google-adk"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .

step "[3/6] .tools/vibe: Vibe-Trading 0.1.19"
[ -x .tools/vibe/bin/python ] || "$PY" -m venv .tools/vibe
.tools/vibe/bin/python -m pip install --upgrade pip
.tools/vibe/bin/python -m pip install vibe-trading-ai==0.1.19

step "[4/6] .tools/aihf: ai-hedge-fund 2.7.2 (optional)"
if [ "$1" = "--with-hedge-fund" ]; then
  ( [ -x .tools/aihf/bin/python ] || "$PY" -m venv .tools/aihf
    .tools/aihf/bin/python -m pip install aihf==2.7.2
    .tools/aihf/bin/python tools/patch_aihf_models.py ) || echo "  ai-hedge-fund install failed; continuing without it"
else
  echo "  skipped (needs a paid data key). Add it later: sh install.sh --with-hedge-fund"
fi

step "[5/6] TradingAgents 1.0.1"
curl -fsSL https://tauric.ai/tradingagents/install.sh | sh -s -- 1.0.1 || echo "  TradingAgents install failed; the Neon step will go straight to Gemini"

step "[6/6] Settings file"
[ -f .env ] || cp .env.example .env

step "Done."
echo "  Check:  .venv/bin/gemini-tradingagents doctor"
echo "  Run:    .venv/bin/gemini-tradingagents AAPL"
