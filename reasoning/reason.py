"""
Node 2 — Reasoning Layer
Feeds observation signals into Gemini and gets back:
- Root cause (with confidence %)
- Hypothesis tree
- Recommended next steps
"""
import os, json
from google import genai
from observation.log_reader import load_signals
from rich.console import Console
from rich.panel import Panel
from rich import box

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
console = Console()

PROMPT = """You are an expert SRE incident commander. Analyze the following incident logs and respond in this exact JSON format:

{{
  "incident_title": "short title",
  "root_cause": "one sentence root cause",
  "confidence_pct": 85,
  "hypothesis_tree": [
    {{"hypothesis": "...", "priority": "HIGH|MED|LOW", "evidence": "..."}}
  ],
  "next_steps": ["step 1", "step 2", "step 3"],
  "blast_radius": ["service1", "service2"]
}}

Incident logs:
{logs}
"""

def reason(signal: dict) -> dict:
    log_text = "\n".join(
        f'{l["time"]} [{l["level"]}] {l["service"]}: {l["msg"]}'
        for l in signal["logs"]
    )
    
    # Mock mode if API quota exhausted
    if os.getenv("MOCK_GEMINI") == "1":
        return mock_reason(signal)
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=PROMPT.format(logs=log_text),
        config={"response_mime_type": "application/json"}
    )
    return json.loads(response.text)

def mock_reason(signal: dict) -> dict:
    """
    Evidence-based incident classifier for mock/offline mode.

    Edge case 5 — Unknown incident type:
      Instead of a hardcoded else→OOM fallback, we score each known pattern
      against the actual log content. If no pattern scores above the confidence
      floor, we return an UNKNOWN result with the raw evidence so the operator
      can investigate rather than acting on a wrong diagnosis.

    Pattern matching priority (highest score wins):
      DB pool exhaustion  → HikariPool / JDBC / max_connections / pg_terminate
      Network / packet    → packet loss / rds-proxy / ECONNREFUSED / AZ
      OOM / crash loop    → OutOfMemoryError / OOMKiller / CrashLoopBackOff / heap
    """
    logs_text = " ".join(l["msg"] for l in signal["logs"])
    services  = signal.get("services", [])

    # Score each pattern by keyword hits in log content
    scores = {
        "db_pool":  sum(kw in logs_text for kw in ["HikariPool", "JDBC", "max_connections", "pg_terminate", "connection pool"]),
        "network":  sum(kw in logs_text for kw in ["packet loss", "rds-proxy", "ECONNREFUSED", "AZ-b", "subnet", "BGP"]),
        "oom":      sum(kw in logs_text for kw in ["OutOfMemoryError", "OOMKiller", "CrashLoopBackOff", "heap space", "memory limit"]),
    }

    best = max(scores, key=scores.get)
    best_score = scores[best]

    # Edge case 5: if no pattern has enough evidence, return UNKNOWN
    if best_score < 2:
        affected = ", ".join(services) if services else "unknown"
        return {
            "incident_title": "Unknown Incident Type",
            "root_cause": f"Insufficient evidence to classify incident. Affected services: {affected}. Manual investigation required.",
            "confidence_pct": 0,
            "hypothesis_tree": [
                {"hypothesis": h, "priority": "MED", "evidence": f"score={scores[p]}"}
                for p, h in [("db_pool", "DB connection issue"), ("network", "Network layer issue"), ("oom", "Memory/process crash")]
            ],
            "next_steps": [
                "Review raw logs manually in incident_simulator/logs/",
                "Check service health dashboards for all affected services",
                "Escalate to on-call SRE with full log trace",
            ],
            "blast_radius": services,
            "_unknown": True,
        }

    if best == "db_pool":
        return {
            "incident_title": "DB Connection Pool Exhaustion",
            "root_cause": "HikariCP connection pool reached max capacity (50/50) due to long-running query blocking connections",
            "confidence_pct": 92,
            "hypothesis_tree": [
                {"hypothesis": "DB connection pool exhausted", "priority": "HIGH", "evidence": "pool size: 50, active: 50, idle: 0"},
                {"hypothesis": "Long-running query blocking pool", "priority": "HIGH", "evidence": "SELECT * FROM orders runtime: 47s"},
                {"hypothesis": "Sudden traffic spike", "priority": "LOW", "evidence": "No traffic anomaly detected in logs"},
            ],
            "next_steps": [
                "Identify and kill long-running query (pid: 2341)",
                "Increase connection pool size from 50 to 100",
                "Add query timeout enforcement (30s max)",
                "Scale RDS read replicas to offload SELECT queries",
            ],
            "blast_radius": ["payment-svc", "order-svc", "api-gateway"],
        }

    if best == "network":
        return {
            "incident_title": "Network Packet Loss Cascade",
            "root_cause": "18% packet loss in subnet-az-b causing RDS connection timeouts and Lambda cold start failures",
            "confidence_pct": 89,
            "hypothesis_tree": [
                {"hypothesis": "Network layer packet loss", "priority": "HIGH", "evidence": "18% packet loss on subnet-az-b"},
                {"hypothesis": "AZ-b infrastructure issue", "priority": "HIGH", "evidence": "0/3 healthy instances in tg-api-az-b"},
                {"hypothesis": "DDoS attack", "priority": "LOW", "evidence": "No abnormal traffic patterns"},
            ],
            "next_steps": [
                "Reroute traffic away from AZ-b",
                "Scale RDS replicas in healthy AZs (a/c)",
                "Pin Lambda functions to AZ-a and AZ-c",
                "Contact AWS support for AZ-b network investigation",
            ],
            "blast_radius": ["api-gateway", "rds-proxy", "lambda", "health-check"],
        }

    # best == "oom"
    return {
        "incident_title": "OOM Kill / CrashLoopBackOff",
        "root_cause": "auth-svc Java heap exhausted (512Mi limit) causing repeated OOMKiller terminations and pod restarts",
        "confidence_pct": 95,
        "hypothesis_tree": [
            {"hypothesis": "Memory leak in auth-svc", "priority": "HIGH", "evidence": "OutOfMemoryError: Java heap space"},
            {"hypothesis": "Insufficient memory allocation", "priority": "MED", "evidence": "512Mi limit may be too low"},
            {"hypothesis": "Traffic spike", "priority": "LOW", "evidence": "No traffic anomaly in logs"},
        ],
        "next_steps": [
            "Increase auth-svc memory limit to 1Gi",
            "Enable heap dump on OOM for analysis",
            "Review recent code changes for memory leaks",
            "Add memory usage alerts before OOM threshold",
        ],
        "blast_radius": ["auth-svc", "api-gateway", "monitoring"],
    }


def display(source: str, result: dict):
    console.print(Panel(
        f'[bold]{result["incident_title"]}[/bold]\n[dim]{source}[/dim]',
        box=box.DOUBLE_EDGE, style="bold white"
    ))
    console.print(f'\n[bold red]Root Cause[/bold red] (confidence: {result["confidence_pct"]}%)')
    console.print(f'  {result["root_cause"]}\n')

    console.print("[bold yellow]Hypothesis Tree[/bold yellow]")
    for h in result["hypothesis_tree"]:
        color = {"HIGH": "red", "MED": "yellow", "LOW": "dim"}.get(h["priority"], "white")
        console.print(f'  [{color}][{h["priority"]}][/{color}] {h["hypothesis"]}')
        console.print(f'        evidence: {h["evidence"]}')

    console.print("\n[bold cyan]Recommended Next Steps[/bold cyan]")
    for i, step in enumerate(result["next_steps"], 1):
        console.print(f'  {i}. {step}')

    console.print(f'\n[bold]Blast Radius:[/bold] {", ".join(result["blast_radius"])}')
    console.print("  → ready for Planner (Node 3)\n")

def run():
    console.print(Panel(
        "[bold cyan]ResilienceOps — Reasoning Layer (Gemini)[/bold cyan]\nAnalyzing incident signals...",
        box=box.HEAVY
    ))
    for signal in load_signals():
        console.print(f'[dim]Analyzing {signal["source"]} ({signal["signal_count"]} signals)...[/dim]')
        result = reason(signal)
        display(signal["source"], result)

if __name__ == "__main__":
    run()
