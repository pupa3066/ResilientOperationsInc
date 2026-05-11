"""
Observation Layer — Node 1
Ingests logs/metrics/traces and surfaces anomaly signals for the reasoning agent.
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from observation.seed_data import INCIDENTS

console = Console()

ANOMALY_RULES = [
    ("error_rate_per_min",          lambda v: v > 100,   "High error rate"),
    ("latency_p99_ms",              lambda v: v > 1000,  "Latency spike"),
    ("packet_loss_pct",             lambda v: v > 5,     "Packet loss"),
    ("traffic_drop_pct",            lambda v: v > 20,    "Traffic drop"),
    ("checkout_failure_rate_pct",   lambda v: v > 10,    "Checkout failures"),
    ("db_active_connections",       lambda v: v >= 100,  "DB pool exhausted"),
    ("long_query_runtime_sec",      lambda v: v > 30,    "Long-running query"),
    ("lambda_cold_start_failure_pct", lambda v: v > 10, "Lambda failures"),
]

def detect_anomalies(metrics: dict) -> list[str]:
    return [label for key, rule, label in ANOMALY_RULES if key in metrics and rule(metrics[key])]

def observe(incident: dict) -> dict:
    anomalies = detect_anomalies(incident["metrics"])
    error_logs = [l for l in incident["logs"] if l["level"] in ("ERROR", "CRITICAL")]
    failed_spans = [t for t in incident["traces"] if t["status"] not in ("ok", "200")]
    return {
        "id":           incident["id"],
        "title":        incident["title"],
        "anomalies":    anomalies,
        "error_logs":   error_logs,
        "failed_spans": failed_spans,
        "metrics":      incident["metrics"],
        "signal_count": len(anomalies) + len(error_logs) + len(failed_spans),
    }

def display(signal: dict):
    severity = "🔴 CRITICAL" if signal["signal_count"] > 8 else "🟠 HIGH" if signal["signal_count"] > 4 else "🟡 MEDIUM"

    console.print(Panel(
        f"[bold]{signal['title']}[/bold]\n[dim]{signal['id']}[/dim]  {severity}",
        box=box.DOUBLE_EDGE, style="bold white"
    ))

    # Anomalies
    t = Table("Anomaly Signal", "Metric Value", box=box.SIMPLE, style="red")
    for a in signal["anomalies"]:
        key = next((k for k, _, l in [
            ("error_rate_per_min", None, "High error rate"),
            ("latency_p99_ms", None, "Latency spike"),
            ("packet_loss_pct", None, "Packet loss"),
            ("traffic_drop_pct", None, "Traffic drop"),
            ("checkout_failure_rate_pct", None, "Checkout failures"),
            ("db_active_connections", None, "DB pool exhausted"),
            ("long_query_runtime_sec", None, "Long-running query"),
            ("lambda_cold_start_failure_pct", None, "Lambda failures"),
        ] if l == a), "—")
        val = signal["metrics"].get(key, "—")
        t.add_row(a, str(val))
    console.print(t)

    # Error logs
    t2 = Table("Time", "Service", "Error", box=box.SIMPLE, style="yellow")
    for l in signal["error_logs"][:4]:  # top 4
        t2.add_row(l["time"][11:19], l["service"], l["msg"][:80])
    console.print(t2)

    # Failed traces
    t3 = Table("Span", "Status", "Duration", box=box.SIMPLE, style="cyan")
    for s in signal["failed_spans"]:
        t3.add_row(s["span"], s["status"], str(s["duration_ms"]) + "ms" if s["duration_ms"] else "dropped")
    console.print(t3)

    console.print(f"  [bold]Total signals:[/bold] {signal['signal_count']}  →  ready for Reasoning Layer\n")

def run():
    console.print(Panel("[bold cyan]ResilienceOps — Observation Layer[/bold cyan]\nIngesting real SRE incident signals...", box=box.HEAVY))
    for incident in INCIDENTS:
        signal = observe(incident)
        display(signal)

if __name__ == "__main__":
    run()
