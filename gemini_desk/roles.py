"""Which Gemini 4 model does which job. Override any role with an env var, e.g. GD_MODEL_JUDGE=gemini-4-neon."""
import datetime as _dt
import os

# Standard paid-tier prices, USD per 1M tokens (input, output), from aistudio.google.com/docs/pricing, checked 2026-11-25.
# Argon and Carbon are $2/$10 until 2026-11-30, then $4/$20. Hydrogen also has a free tier.
PRICES = {
    "gemini-4-hydrogen": (1.50, 7.50),
    "gemini-4-argon": (2.00, 10.00),
    "gemini-4-neon": (3.00, 15.00),
    "gemini-4-carbon": (2.00, 10.00),
    # optional swap for the collector: free tier, $0.75/$3.75 paid until 2026-12-31, then $1.50/$7.50
    "gemini-3.8-flash": (0.75, 3.75),
}
if _dt.date.today() > _dt.date(2026, 11, 30):  # launch promo ends
    PRICES["gemini-4-argon"] = PRICES["gemini-4-carbon"] = (4.00, 20.00)
if _dt.date.today() > _dt.date(2026, 12, 31):
    PRICES["gemini-3.8-flash"] = (1.50, 7.50)

ROLES = {
    # Google: fast daily driver. Squeezes raw data and filings into short notes
    "collector": "gemini-4-hydrogen",
    # Google: flagship reasoning model. Three analysts run in parallel
    "analyst": "gemini-4-argon",
    # Google: mid-tier between Carbon and Hydrogen; #1 of 46 on the Vals Finance Index. Debate + trade plan
    "strategist": "gemini-4-neon",
    # Google: built on Argon, strongest for tasks that test the limits. Risk manager with a veto, final auditor
    "judge": "gemini-4-carbon",
}


def model_for(role):
    return os.environ.get(f"GD_MODEL_{role.upper()}", ROLES[role])
