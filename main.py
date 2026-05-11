"""
ResilienceOps — End-to-End Orchestrator
Runs all 4 nodes in sequence for each incident.
"""
import os
from datetime import datetime, timezone
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich import box

from observation.log_reader import load_signals
from observation.observe import observe as observe_seed, display as display_signal, detect_anomalies
from reasoning.reason import mock_reason
from planner.plan import mock_plan
from hitl.controller import execute, log_decision

console = Console()

def run():
    console.print(Panel(
        "[bold cyan]ResilienceOps[/bold cyan] — AI Incident Commander\n"
        "[dim]Observation → Reasoning → Planning → HITL → Resolution[/dim]",
        box=box.HEAVY
    ))

    signals = load_signals()
    console.print(f"[dim]Loaded {len(signals)} incident(s) from logs[/dim]\n")

    for signal in signals:
        console.print(Rule(f"[bold white]INCIDENT: {signal['source']}[/bold white]"))

        # ── Node 1: Observe ──────────────────────────────────────────────
        console.print("\n[bold]Node 1 — Observation[/bold]")
        console.print(f"  Signals detected: {signal['signal_count']}")
        console.print(f"  Affected services: {', '.join(signal['services'])}")

        # ── Node 2: Reason ───────────────────────────────────────────────
        console.print("\n[bold]Node 2 — Reasoning (Gemini)[/bold]")
        r = mock_reason(signal)
        console.print(f"  Root cause ({r['confidence_pct']}%): {r['root_cause']}")
        console.print(f"  Blast radius: {', '.join(r['blast_radius'])}")

        # ── Node 3: Plan ─────────────────────────────────────────────────
        console.print("\n[bold]Node 3 — Planner[/bold]")
        p = mock_plan(r)
        steps = p["plan"]
        mutating = [s for s in steps if s["type"] == "MUTATING"]
        console.print(f"  {len(steps)} steps generated  ({len(mutating)} require approval)")

        # ── Node 4: HITL ─────────────────────────────────────────────────
        console.print("\n[bold]Node 4 — HITL Controller[/bold]")
        approved = rejected = 0
        for step in steps:
            if step["type"] == "READ_ONLY":
                execute(step, signal["source"], auto=True)
                continue

            console.print(f'\n  [yellow]⚠ Step {step["step"]}[/yellow]: {step["action"]}')
            console.print(f'  Risk: [{"red" if step["risk"]=="HIGH" else "yellow"}]{step["risk"]}[/{"red" if step["risk"]=="HIGH" else "yellow"}]  |  ~{step["estimated_time_min"]} min')

            if os.getenv("AUTO_APPROVE") == "1":
                decision = "y"
                console.print("  [dim]AUTO_APPROVE — approving[/dim]")
            else:
                decision = console.input("  Approve? [y/n/skip]: ").strip().lower()

            if decision == "y":
                execute(step, signal["source"])
                approved += 1
            else:
                console.print(f'  ❌ Step {step["step"]} {"skipped" if decision == "skip" else "rejected"}')
                log_decision(signal["source"], step, "SKIPPED" if decision == "skip" else "REJECTED")
                rejected += 1

        # ── Resolution ───────────────────────────────────────────────────
        console.print(f'\n[bold green]✓ RESOLVED[/bold green]  approved={approved}  rejected={rejected}')
        console.print(f'  Audit log: hitl/audit_log.jsonl\n')

    console.print(Panel("[bold green]All incidents resolved[/bold green]", box=box.HEAVY))

if __name__ == "__main__":
    run()
