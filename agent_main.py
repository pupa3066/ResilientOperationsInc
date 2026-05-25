"""
Multi-Agent Orchestrator (Day 2+)
DetectionAgent → ReasoningAgent → ActionAgent

Edge cases handled here:
  - Cascading incidents (edge case 1):
    After DetectionAgent fires, any incident flagged as cascade_candidate
    is logged as a warning. The ReasoningAgent is told about the cascade
    context so it can factor shared services into its root cause analysis.

  - Incident during remediation (edge case 4):
    After each incident is resolved, load_signals() is called again to
    check if new incidents arrived while remediation was running.
    New incidents are queued and processed in the same session.
"""
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich import box
from agents.detection_agent import DetectionAgent
from agents.reasoning_agent import ReasoningAgent
from agents.action_agent import ActionAgent
from agents.knowledge_agent import KnowledgeAgent
from observation.log_reader import load_signals

console = Console()
MAX_RECHECK_ROUNDS = 3  # prevent infinite loops if new incidents keep arriving


def run():
    console.print(Panel(
        "[bold cyan]ResilienceOps — Multi-Agent System[/bold cyan]\n"
        "[dim]DetectionAgent → ReasoningAgent → ActionAgent[/dim]",
        box=box.HEAVY
    ))

    detection = DetectionAgent()
    reasoning = ReasoningAgent()
    knowledge = KnowledgeAgent()
    action    = ActionAgent()

    # Edge case 4: track already-processed sources to avoid re-running
    processed: set[str] = set()

    for round_num in range(MAX_RECHECK_ROUNDS):
        signals = detection.run()
        new_signals = [s for s in signals if s["source"] not in processed]

        if not new_signals:
            if round_num == 0:
                console.print("[dim]No incidents detected.[/dim]")
            else:
                console.print("[dim]No new incidents detected after remediation.[/dim]")
            break

        console.print()

        for signal in new_signals:
            processed.add(signal["source"])
            console.print(Rule(f"[bold white]{signal['source']}[/bold white]"))

            # Edge case 1: warn about cascading incidents
            if signal.get("cascade_candidates"):
                for c in signal["cascade_candidates"]:
                    console.print(
                        f"[bold yellow]⚡ CASCADE WARNING:[/bold yellow] "
                        f"{signal['source']} shares services {c['shared_services']} "
                        f"with {c['source']} — may be related"
                    )

            result  = reasoning.run(signal)
            kb      = knowledge.run(result)

            # Print RFC + runbook context
            if kb.get("relevant_rfcs"):
                console.print(f"\n[bold blue]📚 Relevant RFCs:[/bold blue]")
                for rfc in kb["relevant_rfcs"][:3]:
                    console.print(f"  • {rfc['id']} — {rfc['title']}")
            if kb.get("similar_incidents"):
                console.print(f"\n[bold blue]🔍 Similar Past Incidents:[/bold blue]")
                for inc in kb["similar_incidents"]:
                    console.print(f"  • [{inc['id']}] {inc['title']} (MTTR: {inc['mttr_min']}min)")
                    console.print(f"    Resolution: {inc['resolution']}")
            if kb.get("recommended_approach"):
                console.print(f"\n[bold green]💡 Recommended Approach:[/bold green]")
                for line in kb["recommended_approach"].splitlines():
                    console.print(f"  {line}")
            console.print()

            summary = action.run(signal, result)

        # Edge case 4: re-check for new incidents that arrived during remediation
        if round_num < MAX_RECHECK_ROUNDS - 1:
            console.print(f"\n[dim]Checking for new incidents that arrived during remediation (round {round_num + 2})...[/dim]")

    console.print(Panel("[bold green]All agents completed[/bold green]", box=box.HEAVY))


if __name__ == "__main__":
    run()
