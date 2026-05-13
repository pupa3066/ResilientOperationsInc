"""
Node 3 — Planner
Takes Gemini root cause output and generates ordered remediation steps.
Classifies each step as READ-ONLY (safe) or MUTATING (needs approval).
"""
import os, json
from google import genai
from reasoning.reason import reason, mock_reason
from observation.log_reader import load_signals
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
console = Console()

PLAN_PROMPT = """You are an SRE planner. Given this incident analysis, generate a detailed remediation plan.

Incident: {title}
Root Cause: {root_cause}
Next Steps: {next_steps}

Return JSON with this structure:
{{
  "plan": [
    {{
      "step": 1,
      "action": "detailed action description",
      "type": "READ_ONLY|MUTATING",
      "estimated_time_min": 5,
      "risk": "LOW|MED|HIGH"
    }}
  ]
}}

Rules:
- READ_ONLY: queries, log checks, metric reads
- MUTATING: restarts, config changes, scaling, deployments
- Order steps by dependency (investigation → diagnosis → fix)
"""

def plan(reasoning_result: dict) -> dict:
    if os.getenv("MOCK_GEMINI") == "1":
        return mock_plan(reasoning_result)
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=PLAN_PROMPT.format(
            title=reasoning_result["incident_title"],
            root_cause=reasoning_result["root_cause"],
            next_steps=json.dumps(reasoning_result["next_steps"])
        ),
        config={"response_mime_type": "application/json"}
    )
    return json.loads(response.text)

def mock_plan(reasoning_result: dict) -> dict:
    """
    Generate a remediation plan with explicit step dependencies.

    Edge case 3 — HITL rejection dependency graph:
      Each MUTATING step declares 'depends_on': a list of step numbers that
      must have been approved before this step can run. If a dependency was
      rejected, the ActionAgent will block all downstream steps automatically.

    Dependency rules per incident type:
      DB pool:     step 4 depends on step 3 (can't resize pool if query not killed)
                   step 5 depends on step 4 (can't deploy if config not updated)
      Packet loss: step 4 depends on step 3 (can't scale replicas before reroute)
                   step 5 depends on step 3 (can't pin Lambda before reroute)
      OOM:         step 4 depends on step 3 (can't apply deployment before editing it)
    """
    title = reasoning_result.get("incident_title", "")

    # Edge case 5: unknown incident — return safe investigation-only plan
    if reasoning_result.get("_unknown"):
        return {
            "plan": [
                {"step": 1, "action": "Review raw logs in incident_simulator/logs/ for all affected services", "type": "READ_ONLY", "estimated_time_min": 5, "risk": "LOW", "depends_on": []},
                {"step": 2, "action": "Check service health dashboards and recent deployment history", "type": "READ_ONLY", "estimated_time_min": 5, "risk": "LOW", "depends_on": []},
                {"step": 3, "action": "Escalate to on-call SRE with full log trace and this report", "type": "READ_ONLY", "estimated_time_min": 2, "risk": "LOW", "depends_on": []},
            ]
        }

    if "DB Connection" in title:
        return {
            "plan": [
                {"step": 1, "action": "Query postgres for active connections: SELECT * FROM pg_stat_activity", "type": "READ_ONLY",  "estimated_time_min": 2,  "risk": "LOW", "depends_on": []},
                {"step": 2, "action": "Identify long-running query (pid: 2341) blocking pool",                 "type": "READ_ONLY",  "estimated_time_min": 3,  "risk": "LOW", "depends_on": []},
                {"step": 3, "action": "Kill blocking query: SELECT pg_terminate_backend(2341)",                "type": "MUTATING",   "estimated_time_min": 1,  "risk": "MED", "depends_on": []},
                {"step": 4, "action": "Increase HikariCP pool size from 50 to 100 in payment-svc config",     "type": "MUTATING",   "estimated_time_min": 5,  "risk": "MED", "depends_on": [3]},
                {"step": 5, "action": "Deploy updated payment-svc with new pool config",                      "type": "MUTATING",   "estimated_time_min": 8,  "risk": "HIGH","depends_on": [4]},
                {"step": 6, "action": "Add query timeout enforcement (30s max) to prevent future blocks",     "type": "MUTATING",   "estimated_time_min": 10, "risk": "MED", "depends_on": []},
            ]
        }

    if "Packet Loss" in title:
        return {
            "plan": [
                {"step": 1, "action": "Check VPC flow logs for packet loss metrics in AZ-b",          "type": "READ_ONLY", "estimated_time_min": 3,  "risk": "LOW",  "depends_on": []},
                {"step": 2, "action": "Verify target group health: 0/3 healthy in tg-api-az-b",       "type": "READ_ONLY", "estimated_time_min": 2,  "risk": "LOW",  "depends_on": []},
                {"step": 3, "action": "Reroute ALB traffic away from AZ-b to AZ-a/c",                 "type": "MUTATING",  "estimated_time_min": 5,  "risk": "HIGH", "depends_on": []},
                {"step": 4, "action": "Scale RDS read replicas in AZ-a and AZ-c",                     "type": "MUTATING",  "estimated_time_min": 10, "risk": "MED",  "depends_on": [3]},
                {"step": 5, "action": "Update Lambda VPC config to pin to AZ-a/c subnets",            "type": "MUTATING",  "estimated_time_min": 7,  "risk": "MED",  "depends_on": [3]},
                {"step": 6, "action": "Open AWS support ticket for AZ-b network investigation",       "type": "READ_ONLY", "estimated_time_min": 5,  "risk": "LOW",  "depends_on": []},
            ]
        }

    # OOM / CrashLoop
    return {
        "plan": [
            {"step": 1, "action": "Check auth-svc pod status: kubectl get pods -l app=auth-svc",          "type": "READ_ONLY", "estimated_time_min": 1,  "risk": "LOW", "depends_on": []},
            {"step": 2, "action": "Review OOM events: kubectl describe pod auth-svc-7d9f",                "type": "READ_ONLY", "estimated_time_min": 2,  "risk": "LOW", "depends_on": []},
            {"step": 3, "action": "Increase auth-svc memory limit from 512Mi to 1Gi in deployment.yaml",  "type": "MUTATING",  "estimated_time_min": 3,  "risk": "MED", "depends_on": []},
            {"step": 4, "action": "Apply updated deployment: kubectl apply -f auth-svc-deployment.yaml",  "type": "MUTATING",  "estimated_time_min": 5,  "risk": "HIGH","depends_on": [3]},
            {"step": 5, "action": "Enable heap dump on OOM: -XX:+HeapDumpOnOutOfMemoryError",             "type": "MUTATING",  "estimated_time_min": 4,  "risk": "LOW", "depends_on": []},
            {"step": 6, "action": "Monitor pod restart count for next 10 minutes",                        "type": "READ_ONLY", "estimated_time_min": 10, "risk": "LOW", "depends_on": []},
        ]
    }

def display(source: str, reasoning_result: dict, plan_result: dict):
    console.print(Panel(
        f'[bold]{reasoning_result["incident_title"]}[/bold]\n[dim]{source}[/dim]',
        box=box.DOUBLE_EDGE, style="bold cyan"
    ))
    
    t = Table("Step", "Action", "Type", "Time", "Risk", box=box.SIMPLE)
    for p in plan_result["plan"]:
        color = {"READ_ONLY": "green", "MUTATING": "yellow"}.get(p["type"], "white")
        risk_color = {"LOW": "dim", "MED": "yellow", "HIGH": "red"}.get(p["risk"], "white")
        t.add_row(
            str(p["step"]),
            p["action"][:70],
            f'[{color}]{p["type"]}[/{color}]',
            f'{p["estimated_time_min"]}m',
            f'[{risk_color}]{p["risk"]}[/{risk_color}]'
        )
    console.print(t)
    
    mutating = [p for p in plan_result["plan"] if p["type"] == "MUTATING"]
    console.print(f'\n[bold yellow]⚠ {len(mutating)} steps require HITL approval[/bold yellow]')
    console.print('  → ready for HITL Controller (Node 5)\n')

def run():
    console.print(Panel(
        "[bold cyan]ResilienceOps — Planner (Node 3)[/bold cyan]\nGenerating remediation plans...",
        box=box.HEAVY
    ))
    
    for signal in load_signals():
        reasoning_result = mock_reason(signal) if os.getenv("MOCK_GEMINI") == "1" else reason(signal)
        plan_result = plan(reasoning_result)
        display(signal["source"], reasoning_result, plan_result)

if __name__ == "__main__":
    run()
