"""
Node 4 — HITL Controller (Human-in-the-Loop)
Presents MUTATING steps to SRE for approval before execution.
Auto-executes READ_ONLY steps. Logs all decisions.
"""
import os, json
from datetime import datetime, timezone
from pathlib import Path
from observation.log_reader import load_signals
from reasoning.reason import mock_reason
from planner.plan import mock_plan
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()
AUDIT_LOG = Path("hitl/audit_log.jsonl")
AUDIT_LOG.parent.mkdir(exist_ok=True)

def log_decision(incident: str, step: dict, decision: str):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "incident": incident,
        "step": step["step"],
        "action": step["action"],
        "type": step["type"],
        "decision": decision,
    }
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

def execute(step: dict, incident: str, auto: bool = False):
    """Simulate execution — in production this calls real tool APIs."""
    label = "[dim](auto)[/dim]" if auto else "[bold green](approved)[/bold green]"
    console.print(f'  ✅ Step {step["step"]} executed {label}: {step["action"][:70]}')
    log_decision(incident, step, "AUTO" if auto else "APPROVED")

def run():
    console.print(Panel(
        "[bold cyan]ResilienceOps — HITL Controller (Node 4)[/bold cyan]\nReviewing remediation plans for approval...",
        box=box.HEAVY
    ))

    for signal in load_signals():
        reasoning_result = mock_reason(signal)
        plan_result = mock_plan(reasoning_result)
        steps = plan_result["plan"]
        title = reasoning_result["incident_title"]

        console.print(Panel(
            f'[bold]{title}[/bold]\n[dim]{signal["source"]}[/dim]',
            box=box.DOUBLE_EDGE, style="bold white"
        ))

        for step in steps:
            if step["type"] == "READ_ONLY":
                execute(step, signal["source"], auto=True)
                continue

            # MUTATING — requires approval
            console.print(f'\n[bold yellow]⚠ APPROVAL REQUIRED — Step {step["step"]}[/bold yellow]')
            console.print(f'  Action : {step["action"]}')
            console.print(f'  Risk   : [{"red" if step["risk"] == "HIGH" else "yellow"}]{step["risk"]}[/{"red" if step["risk"] == "HIGH" else "yellow"}]')
            console.print(f'  Time   : ~{step["estimated_time_min"]} min')

            if os.getenv("AUTO_APPROVE") == "1":
                decision = "y"
                console.print('  [dim]AUTO_APPROVE=1 — auto-approving[/dim]')
            else:
                decision = console.input('  Approve? [y/n/skip]: ').strip().lower()

            if decision == "y":
                execute(step, signal["source"])
            elif decision == "skip":
                console.print(f'  ⏭ Step {step["step"]} skipped')
                log_decision(signal["source"], step, "SKIPPED")
            else:
                console.print(f'  ❌ Step {step["step"]} rejected')
                log_decision(signal["source"], step, "REJECTED")

        console.print()

    console.print(Panel(
        f'[bold green]All incidents processed[/bold green]\nAudit log: {AUDIT_LOG}',
        box=box.HEAVY
    ))

if __name__ == "__main__":
    run()
