"""
Multi-Agent Orchestrator (Day 2)
DetectionAgent → ReasoningAgent → ActionAgent
"""
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich import box
from agents.detection_agent import DetectionAgent
from agents.reasoning_agent import ReasoningAgent
from agents.action_agent import ActionAgent

console = Console()

def run():
    console.print(Panel(
        "[bold cyan]ResilienceOps — Multi-Agent System[/bold cyan]\n"
        "[dim]DetectionAgent → ReasoningAgent → ActionAgent[/dim]",
        box=box.HEAVY
    ))

    detection = DetectionAgent()
    reasoning = ReasoningAgent()
    action    = ActionAgent()

    signals = detection.run()
    console.print()

    for signal in signals:
        console.print(Rule(f"[bold white]{signal['source']}[/bold white]"))
        result  = reasoning.run(signal)
        summary = action.run(signal, result)

    console.print(Panel("[bold green]All agents completed[/bold green]", box=box.HEAVY))

if __name__ == "__main__":
    run()
