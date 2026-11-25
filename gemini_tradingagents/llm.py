"""Gemini API client: plain HTTPS (no SDK), disk cache, token and cost accounting, dry-run mode."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .roles import PRICES

BASE_URL = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
CACHE_DIR = Path(os.environ.get("GD_CACHE_DIR", ".gd_cache"))


class GeminiError(RuntimeError):
    pass


def billing_hint(model, msg):
    import re
    if "free_tier" in msg and "limit: 0" in msg:
        return (f"Model {model} needs billing on your Google project (AI Studio > Set up billing), "
                f"or set GD_MODEL_*=gemini-4-hydrogen in .env")
    if "free_tier" in msg:
        q = re.search(r'"quotaValue": "(\d+)"', msg)
        d = re.search(r'"retryDelay": "(\d+)s"', msg)
        return (f"Free-tier limit reached for {model}" + (f" ({q.group(1)} requests/day)" if q else "")
                + (f"; resets in ~{int(d.group(1)) // 3600} h" if d else "") + ". Enable billing in AI Studio for full runs.")
    return None


class Usage:
    def __init__(self):
        self.rows = []  # (role, model, in_tokens, out_tokens, usd, seconds)

    def add(self, role, model, tin, tout, secs):
        pin, pout = PRICES.get(model, (0.0, 0.0))
        usd = tin / 1e6 * pin + tout / 1e6 * pout
        self.rows.append((role, model, tin, tout, usd, secs))

    def table(self):
        lines = ["| Role | Model | Input tokens | Output tokens | Cost (USD) | Seconds |", "|---|---|---|---|---|---|"]
        for r in self.rows:
            lines.append(f"| {r[0]} | {r[1]} | {r[2]:,} | {r[3]:,} | {r[4]:.4f} | {r[5]:.1f} |")
        tot = sum(r[4] for r in self.rows)
        lines.append(f"| **Total** | | {sum(r[2] for r in self.rows):,} | {sum(r[3] for r in self.rows):,} | **{tot:.4f}** | {sum(r[5] for r in self.rows):.1f} |")
        return "\n".join(lines)


class Gemini:
    """One client for every role. `dry_run` returns a placeholder instead of calling the API."""

    def __init__(self, api_key=None, dry_run=False, use_cache=True):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.dry_run = dry_run
        self.use_cache = use_cache
        self.usage = Usage()
        if not dry_run and not self.api_key:
            raise SystemExit("No GEMINI_API_KEY found. Put it in .env (see .env.example) or run with --dry-run.")

    def ask(self, role, model, system, prompt, json_mode=False, schema=None):
        json_mode = json_mode or schema is not None
        key = hashlib.sha256(json.dumps([model, system, prompt, json_mode, schema]).encode()).hexdigest()[:24]
        cpath = CACHE_DIR / f"{key}.json"
        if self.use_cache and cpath.exists() and not self.dry_run:
            hit = json.loads(cpath.read_text(encoding="utf-8"))
            self.usage.add(role + " (cached)", model, 0, 0, 0.0)
            return hit["text"]
        if self.dry_run:
            text = f"[dry-run: {role} on {model}; prompt was {len(prompt):,} chars]"
            if json_mode:
                text = json.dumps({"dry_run": True, "role": role, "verdict": "NO-GO", "reasons": ["dry run, no model called"]})
            self.usage.add(role + " (dry-run, input estimate)", model, len(prompt) // 4, 0, 0.0)
            return text
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            # Gemini 4 ignores temperature/top_p/top_k, so none are sent.
            "generationConfig": {},
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
            if schema:  # structured output: the API enforces the shape, Python still validates
                body["generationConfig"]["responseSchema"] = schema
        req = urllib.request.Request(
            f"{BASE_URL}/models/{model}:generateContent",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
        )
        t0 = time.time()
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    data = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="ignore")[:400]
                if e.code in (429, 500, 503) and attempt < 3:
                    time.sleep(2 ** attempt * 3)
                    continue
                raise GeminiError(billing_hint(model, msg) or f"Gemini API error {e.code} for {model} ({role}): {msg[:200]}")
        cand = (data.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
        um = data.get("usageMetadata", {})
        self.usage.add(role, model, um.get("promptTokenCount", 0), um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0), time.time() - t0)
        if self.use_cache:
            CACHE_DIR.mkdir(exist_ok=True)
            cpath.write_text(json.dumps({"model": model, "text": text}), encoding="utf-8")
        return text


def parse_json(text):
    """Models sometimes wrap JSON in ``` fences; strip them before parsing."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return {"verdict": "NO-GO", "reasons": ["model returned unparseable JSON"], "raw": text[:2000]}
