"""Fixture tests for reading the donors' real outputs (formats taken from their source)."""
import json
import os
import time
from gemini_tradingagents import stages


def test_vibe_answer_from_trace_and_metrics(tmp_path, monkeypatch):
    run_dir = tmp_path / "runs" / "r1"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "artifacts" / "metrics.csv").write_text("strategy,cagr,sharpe\nbuy_and_hold,0.21,1.1\n", encoding="utf-8")
    monkeypatch.setattr(stages, "_vibe_trace_answer", lambda run_id: "ANSWER for " + run_id)
    stdout = json.dumps({"status": "success", "run_id": "r1", "run_dir": str(run_dir), "reason": ""})
    out = stages._vibe_answer(stdout, time.time())
    assert out.startswith("ANSWER for r1") and "buy_and_hold,0.21,1.1" in out


def test_committee_reads_swarm_run_json(tmp_path, monkeypatch):
    home = tmp_path / ".vibe-home"
    run = home / "swarm" / "runs" / "swarm-1"
    (run / "tasks").mkdir(parents=True)
    monkeypatch.setenv("VIBE_TRADING_HOME", str(home))
    monkeypatch.setattr(stages, "_run", lambda name, cmd, env, dry_run, cwd=None: (
        run.joinpath("run.json").write_text(json.dumps({"status": "completed", "final_report": "PM: buy small",
            "tasks": [{"agent_id": "bull_advocate", "summary": "bull case"}, {"agent_id": "bear_advocate", "summary": "bear case"}]}), encoding="utf-8"),
        {"stage": name, "status": "ok", "command": "x", "output": "", "stderr": ""})[1])
    r = stages.committee("AAPL")
    assert "PM: buy small" in r["output"] and "[bull_advocate] bull case" in r["output"] and r["status"] == "ok"


def test_committee_429_is_reported(tmp_path, monkeypatch):
    home = tmp_path / ".vibe-home"
    run = home / "swarm" / "runs" / "swarm-2"
    (run / "tasks").mkdir(parents=True)
    monkeypatch.setenv("VIBE_TRADING_HOME", str(home))

    def fake_run(name, cmd, env, dry_run, cwd=None):
        run.joinpath("run.json").write_text(json.dumps({"status": "failed", "final_report": None, "tasks": []}), encoding="utf-8")
        run.joinpath("tasks", "t.json").write_text(json.dumps({"error": "OpenAIRateLimitError: Error code: 429"}), encoding="utf-8")
        return {"stage": name, "status": "exit 1", "command": "x", "output": "", "stderr": ""}
    monkeypatch.setattr(stages, "_run", fake_run)
    r = stages.committee("AAPL")
    assert r["status"] == "quota (429)" and "429" in r["stderr"]


def test_cli_out_flag_before_a_command(tmp_path, capsys):
    from gemini_tradingagents import cli
    assert cli.main(["--out", str(tmp_path), "score"]) == 0
    assert "No GO calls" in capsys.readouterr().out
