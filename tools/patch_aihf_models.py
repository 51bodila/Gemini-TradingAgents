"""Add the four Gemini 4 models to ai-hedge-fund's model list.

aihf routes any model id that is not in hedge_fund/llm/api_models.json to Anthropic, so gemini-4-* ids must be listed
with provider "Google". This edits the installed copy only; run again after upgrading aihf.
"""
import json
import sys
from pathlib import Path

try:
    import hedge_fund.llm as llm_pkg
except ImportError:
    sys.exit("aihf is not installed in this Python environment")

path = Path(llm_pkg.__file__).parent / "api_models.json"
models = json.loads(path.read_text(encoding="utf-8"))
have = {m["model_name"] for m in models}
added = []
for mid, name in [("gemini-4-hydrogen", "Gemini 4 Hydrogen"), ("gemini-4-argon", "Gemini 4 Argon"),
                  ("gemini-4-neon", "Gemini 4 Neon"), ("gemini-4-carbon", "Gemini 4 Carbon")]:
    if mid not in have:
        models.append({"display_name": name, "model_name": mid, "provider": "Google"})
        added.append(mid)
path.write_text(json.dumps(models, indent=2), encoding="utf-8")
print(f"{path}: added {', '.join(added) or 'nothing (already listed)'}")
