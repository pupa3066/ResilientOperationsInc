#!/usr/bin/env python3
"""
ResilienceOps Debug Tools

CLI for inspecting, testing, and debugging all system components.

Usage:
  python debug.py health          — check all integrations
  python debug.py logs            — tail and parse incident logs
  python debug.py pipeline        — dry-run pipeline with verbose output
  python debug.py incident <id>   — inspect a specific incident in detail
  python debug.py history         — show historical incident store
  python debug.py replay <log>    — replay a log with debug tracing
  python debug.py k8s <service>   — query k8s context for a service
  python debug.py elastic <svc>   — query elastic MCP for a service
  python debug.py agents          — test each agent in isolation
  python debug.py api             — run API endpoint smoke tests
"""
import os, sys, json, time, traceback
from pathlib import Path
from datetime import datetime, timezone

os.environ.setdefault("MOCK_GEMINI", "1")
os.environ.setdefault("GEMINI_API_KEY", "debug")

sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


def cmd_health():
    """Check health of all integrations."""
    console.print(Panel("[bold]System Health Check[/bold]", box=box.HEAVY))

    # Elastic MCP
    from observation.elastic_mcp import ElasticMCP
    mcp = ElasticMCP()
    h = mcp.health()
    status_color = {"ok": "green", "stub": "yellow", "unreachable": "red"}.get(h["status"], "red")
    console.print(f"  Elastic MCP: [{status_color}]{h['status']}[/{status_color}] (url={h.get('url')})")

    # K8s
    from observation.k8s import K8sObserver
    k8s = K8sObserver()
    h = k8s.health()
    status_color = {"ok": "green", "stub": "yellow"}.get(h["status"], "red")
    console.print(f"  Kubernetes:  [{status_color}]{h['status']}[/{status_color}] (ns={h.get('namespace')})")

    # Gemini
    gemini_mode = "live" if os.getenv("MOCK_GEMINI") != "1" and os.getenv("GEMINI_API_KEY") not in (None, "", "debug") else "mock"
    color = "green" if gemini_mode == "live" else "yellow"
    console.print(f"  Gemini:      [{color}]{gemini_mode}[/{color}]")

    # History store
    import history
    stats = history.stats()
    console.print(f"  History:     [cyan]{stats['total']} records[/cyan] {stats.get('by_type', {})}")

    # Log files
    from observation.log_reader import LOG_DIR
    logs = list(LOG_DIR.glob("incident-*.log"))
    console.print(f"  Log files:   [cyan]{len(logs)}[/cyan] in {LOG_DIR}")

    # API import
    try:
        import api
        console.print(f"  API module:  [green]OK[/green] (v{api.app.version})")
    except Exception as e:
        console.print(f"  API module:  [red]FAIL[/red] ({e})")


def cmd_logs():
    """Parse and display all incident logs with error highlighting."""
    from observation.log_reader import LOG_DIR, parse_log

    console.print(Panel("[bold]Incident Log Inspector[/bold]", box=box.HEAVY))

    log_files = sorted(LOG_DIR.glob("incident-*.log"))
    if not log_files:
        console.print("[red]No log files found[/red]")
        return

    for log_file in log_files:
        entries = parse_log(log_file)
        errors = [e for e in entries if e["level"] in ("ERROR", "CRITICAL")]
        services = list(dict.fromkeys(e["service"] for e in errors))

        color = "red" if len(errors) >= 10 else "yellow" if errors else "green"
        console.print(f"\n[{color}]● {log_file.name}[/{color}] — {len(entries)} lines, {len(errors)} errors, services: {services}")

        # Show first 3 errors
        for e in errors[:3]:
            console.print(f"    [{e['level']}] {e['time']} {e['service']}: {e['msg']}")
        if len(errors) > 3:
            console.print(f"    [dim]... +{len(errors)-3} more errors[/dim]")


def cmd_pipeline():
    """Dry-run the full pipeline with verbose debug output."""
    console.print(Panel("[bold]Pipeline Debug Run[/bold]", box=box.HEAVY))

    from agents.detection_agent import DetectionAgent
    from agents.reasoning_agent import ReasoningAgent
    from agents.knowledge_agent import KnowledgeAgent
    from planner.plan import mock_plan
    from observation.elastic_mcp import ElasticMCP
    from observation.k8s import K8sObserver
    import history

    t0 = time.time()

    # Detection
    console.print("\n[bold cyan]1. Detection[/bold cyan]")
    detection = DetectionAgent()
    try:
        signals = detection.run()
        console.print(f"   ✓ {len(signals)} signals fired")
    except Exception as e:
        console.print(f"   [red]✗ Detection failed: {e}[/red]")
        traceback.print_exc()
        return

    if not signals:
        console.print("   [dim]Nothing to process[/dim]")
        return

    # Process first signal in detail
    signal = signals[0]
    console.print(f"   Using: {signal['source']} ({signal['signal_count']} signals)")

    # Reasoning
    console.print("\n[bold cyan]2. Reasoning[/bold cyan]")
    reasoning_agent = ReasoningAgent()
    try:
        t1 = time.time()
        reasoning = reasoning_agent.run(signal)
        console.print(f"   ✓ {reasoning['incident_title']} ({reasoning['confidence_pct']}%) [{time.time()-t1:.2f}s]")
        console.print(f"   Type: {reasoning.get('incident_type', 'N/A')}")
        console.print(f"   Blast: {reasoning.get('blast_radius')}")
    except Exception as e:
        console.print(f"   [red]✗ Reasoning failed: {e}[/red]")
        traceback.print_exc()
        return

    # Knowledge
    console.print("\n[bold cyan]3. Knowledge[/bold cyan]")
    knowledge_agent = KnowledgeAgent()
    try:
        kb = knowledge_agent.run(reasoning)
        hist_matches = history.find_similar(reasoning)
        console.print(f"   ✓ RFCs: {len(kb.get('relevant_rfcs', []))}, Runbooks: {len(kb.get('runbooks', []))}")
        console.print(f"   ✓ Historical matches: {len(hist_matches)}")
    except Exception as e:
        console.print(f"   [red]✗ Knowledge failed: {e}[/red]")
        traceback.print_exc()

    # Planning
    console.print("\n[bold cyan]4. Planning[/bold cyan]")
    try:
        plan = mock_plan(reasoning)
        steps = plan["plan"]
        mutating = [s for s in steps if s["type"] == "MUTATING"]
        console.print(f"   ✓ {len(steps)} steps ({len(mutating)} MUTATING)")
        for s in steps:
            icon = "🔒" if s["type"] == "MUTATING" else "👁"
            console.print(f"     {icon} Step {s['step']}: {s['action'][:60]}")
    except Exception as e:
        console.print(f"   [red]✗ Planning failed: {e}[/red]")
        traceback.print_exc()

    # Elastic MCP
    console.print("\n[bold cyan]5. Elastic MCP[/bold cyan]")
    try:
        elastic = ElasticMCP().query(signal)
        console.print(f"   ✓ Mode: {elastic.get('mode')}, Signals: {elastic.get('signals_used')}")
    except Exception as e:
        console.print(f"   [red]✗ Elastic failed: {e}[/red]")

    # K8s
    console.print("\n[bold cyan]6. Kubernetes[/bold cyan]")
    try:
        k8s = K8sObserver().query(signal.get("services", []))
        console.print(f"   ✓ Mode: {k8s.get('mode')}, Pods: {len(k8s.get('pod_status', []))}, Events: {len(k8s.get('events', []))}")
    except Exception as e:
        console.print(f"   [red]✗ K8s failed: {e}[/red]")

    console.print(f"\n[dim]Total time: {time.time()-t0:.2f}s[/dim]")


def cmd_incident(inc_id: str):
    """Inspect a specific incident via the API."""
    from fastapi.testclient import TestClient
    from api import app

    client = TestClient(app)

    # Try to find it — might need to run pipeline first
    r = client.get(f"/incidents/{inc_id}")
    if r.status_code == 404:
        console.print(f"[red]Incident {inc_id} not found.[/red] Run 'python debug.py api' first to create incidents.")
        return

    d = r.json()
    console.print(Panel(f"[bold]{d['title']}[/bold]\n{d['id']} — {d['status']}", box=box.DOUBLE_EDGE))
    console.print(f"  Root cause: {d['root_cause']}")
    console.print(f"  Confidence: {d['confidence_pct']}%")
    console.print(f"  Blast radius: {d['blast_radius']}")

    # Steps
    t = Table("Step", "Action", "Type", "Decision", box=box.SIMPLE)
    for s in d["steps"]:
        dec_color = {"auto": "green", "approve": "green", "reject": "red", "blocked": "dim", "pending": "yellow"}.get(s["decision"], "white")
        t.add_row(str(s["step"]), s["action"][:55], s["type"], f"[{dec_color}]{s['decision']}[/{dec_color}]")
    console.print(t)

    # K8s context
    k8s = d.get("k8s_context", {})
    if k8s:
        console.print(f"\n  [cyan]K8s:[/cyan] mode={k8s.get('mode')}, pods={len(k8s.get('pod_status', []))}")
        for pod in k8s.get("pod_status", [])[:3]:
            color = "green" if pod.get("ready") else "red"
            console.print(f"    [{color}]{pod['name']}[/{color}] phase={pod.get('phase')} restarts={pod.get('restarts')}")

    # Elastic context
    elastic = d.get("elastic_context", {})
    if elastic:
        console.print(f"\n  [cyan]Elastic:[/cyan] mode={elastic.get('mode')}, signals={elastic.get('signals_used')}")

    # Knowledge
    kb = d.get("knowledge", {})
    if kb:
        console.print(f"\n  [cyan]Knowledge:[/cyan] RFCs={len(kb.get('relevant_rfcs', []))}, history={len(kb.get('historical_matches', []))}")


def cmd_history():
    """Display the historical incident store."""
    import history

    records = history.load_all()
    if not records:
        console.print("[dim]No historical incidents stored yet. Resolve an incident first.[/dim]")
        return

    console.print(Panel(f"[bold]Historical Incidents ({len(records)} total)[/bold]", box=box.HEAVY))

    t = Table("ID", "Type", "Title", "Services", "Resolved", box=box.SIMPLE)
    for r in records:
        t.add_row(
            r["id"][:8],
            r.get("incident_type", "?"),
            r.get("title", "?")[:40],
            ", ".join(r.get("services", [])[:3]),
            r.get("resolved_at", "?")[:19],
        )
    console.print(t)

    stats = history.stats()
    console.print(f"\n[dim]By type: {stats['by_type']}[/dim]")


def cmd_replay(log_name: str):
    """Replay a log with debug tracing."""
    from observation.log_reader import LOG_DIR, parse_log
    from agents.reasoning_agent import ReasoningAgent
    import history

    log_path = LOG_DIR / log_name
    if not log_path.exists():
        console.print(f"[red]Log not found: {log_name}[/red]")
        console.print(f"Available: {[f.name for f in sorted(LOG_DIR.glob('incident-*.log'))]}")
        return

    console.print(Panel(f"[bold]Replay: {log_name}[/bold]", box=box.HEAVY))

    # Parse
    entries = parse_log(log_path)
    errors = [e for e in entries if e["level"] in ("ERROR", "CRITICAL")]
    services = list(dict.fromkeys(e["service"] for e in errors))
    console.print(f"  Parsed: {len(entries)} lines, {len(errors)} errors, services={services}")

    signal = {
        "id": log_path.stem.upper().replace("-", "_"),
        "source": log_name,
        "logs": entries,
        "error_logs": errors,
        "services": services,
        "signal_count": len(errors),
        "cascade_candidates": [],
    }

    # Reason
    agent = ReasoningAgent()
    t0 = time.time()
    reasoning = agent.run(signal)
    elapsed = time.time() - t0

    console.print(f"\n  [bold]Result:[/bold] {reasoning['incident_title']}")
    console.print(f"  Type: {reasoning.get('incident_type')}")
    console.print(f"  Confidence: {reasoning['confidence_pct']}%")
    console.print(f"  Root cause: {reasoning['root_cause']}")
    console.print(f"  Time: {elapsed:.3f}s")

    # Compare to ground truth
    past = [h for h in history.load_all() if h.get("source") == log_name]
    if past:
        gt = past[-1]
        match = reasoning.get("incident_type") == gt.get("incident_type")
        color = "green" if match else "red"
        console.print(f"\n  [bold]Ground Truth:[/bold] {gt['title']} (type={gt['incident_type']})")
        console.print(f"  [{color}]Type match: {match}[/{color}]")
    else:
        console.print(f"\n  [dim]No ground truth in history for this log[/dim]")


def cmd_k8s(service: str):
    """Query k8s context for a service."""
    from observation.k8s import K8sObserver

    k8s = K8sObserver()
    console.print(f"[bold]K8s Query: {service}[/bold] (mode={'live' if k8s.live else 'stub'})")

    result = k8s.query([service])
    console.print(json.dumps(result, indent=2, default=str))


def cmd_elastic(service: str):
    """Query elastic MCP for a service."""
    from observation.elastic_mcp import ElasticMCP

    mcp = ElasticMCP()
    console.print(f"[bold]Elastic MCP Query: {service}[/bold] (mode={'live' if mcp.live else 'stub'})")

    signal = {"services": [service], "error_logs": [{"msg": "debug query"}], "signal_count": 5}
    result = mcp.query(signal)
    console.print(json.dumps(result, indent=2, default=str))


def cmd_agents():
    """Test each agent in isolation."""
    from observation.log_reader import load_signals

    console.print(Panel("[bold]Agent Isolation Tests[/bold]", box=box.HEAVY))

    signals = load_signals()
    if not signals:
        console.print("[red]No signals available[/red]")
        return

    signal = signals[0]
    console.print(f"Using signal: {signal['source']} ({signal['signal_count']} errors)\n")

    # DetectionAgent
    console.print("[bold cyan]DetectionAgent[/bold cyan]")
    try:
        from agents.detection_agent import DetectionAgent
        d = DetectionAgent()
        fired = d.run()
        console.print(f"  ✓ Fired {len(fired)} incidents")
    except Exception as e:
        console.print(f"  [red]✗ {e}[/red]")

    # ReasoningAgent
    console.print("[bold cyan]ReasoningAgent[/bold cyan]")
    try:
        from agents.reasoning_agent import ReasoningAgent
        r = ReasoningAgent()
        result = r.run(signal)
        console.print(f"  ✓ {result['incident_title']} ({result['confidence_pct']}%)")
    except Exception as e:
        console.print(f"  [red]✗ {e}[/red]")
        traceback.print_exc()
        return

    # KnowledgeAgent
    console.print("[bold cyan]KnowledgeAgent[/bold cyan]")
    try:
        from agents.knowledge_agent import KnowledgeAgent
        k = KnowledgeAgent()
        kb = k.run(result)
        console.print(f"  ✓ RFCs={len(kb['relevant_rfcs'])}, runbooks={len(kb['runbooks'])}, similar={len(kb['similar_incidents'])}")
    except Exception as e:
        console.print(f"  [red]✗ {e}[/red]")

    # ActionAgent
    console.print("[bold cyan]ActionAgent[/bold cyan]")
    try:
        from agents.action_agent import ActionAgent
        a = ActionAgent()
        summary = a.run(signal, result)
        console.print(f"  ✓ {summary}")
    except Exception as e:
        console.print(f"  [red]✗ {e}[/red]")


def cmd_api():
    """Run API endpoint smoke tests."""
    from fastapi.testclient import TestClient
    from api import app

    console.print(Panel("[bold]API Smoke Tests[/bold]", box=box.HEAVY))
    client = TestClient(app)

    tests = [
        ("GET", "/health", None, 200),
        ("GET", "/", None, 200),
        ("POST", "/incidents/run", None, 201),
        ("GET", "/incidents", None, 200),
        ("GET", "/history", None, 200),
        ("GET", "/history/stats", None, 200),
        ("GET", "/k8s/payment-svc", None, 200),
        ("POST", "/replay/incident-1.log", None, 200),
    ]

    passed = 0
    for method, path, body, expected in tests:
        try:
            if method == "GET":
                r = client.get(path)
            else:
                r = client.post(path, json=body)
            ok = r.status_code == expected
            color = "green" if ok else "red"
            console.print(f"  [{color}]{'✓' if ok else '✗'}[/{color}] {method} {path} → {r.status_code}")
            if ok:
                passed += 1
            else:
                console.print(f"    [dim]{r.text[:100]}[/dim]")
        except Exception as e:
            console.print(f"  [red]✗[/red] {method} {path} → EXCEPTION: {e}")

    # Test approval flow
    r = client.get("/incidents")
    incidents = r.json()
    if incidents:
        inc_id = incidents[0]["id"]
        r = client.get(f"/incidents/{inc_id}")
        if r.status_code == 200:
            console.print(f"  [green]✓[/green] GET /incidents/{inc_id} → 200")
            passed += 1

            # Test WebSocket
            try:
                with client.websocket_connect(f"/incidents/{inc_id}/ws") as ws:
                    msg = ws.receive_json()
                    console.print(f"  [green]✓[/green] WS /incidents/{inc_id}/ws → connected (event={msg['event']})")
                    passed += 1
            except Exception as e:
                console.print(f"  [red]✗[/red] WS → {e}")

    console.print(f"\n  [bold]{passed}/{len(tests)+2} passed[/bold]")


# ── CLI dispatch ──────────────────────────────────────────────────────────────

COMMANDS = {
    "health": cmd_health,
    "logs": cmd_logs,
    "pipeline": cmd_pipeline,
    "incident": cmd_incident,
    "history": cmd_history,
    "replay": cmd_replay,
    "k8s": cmd_k8s,
    "elastic": cmd_elastic,
    "agents": cmd_agents,
    "api": cmd_api,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        console.print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    fn = COMMANDS[cmd]
    import inspect
    params = inspect.signature(fn).parameters
    if params and not args:
        console.print(f"[red]Missing argument for '{cmd}'[/red]")
        console.print(f"  Usage: python debug.py {cmd} <{list(params.keys())[0]}>")
        sys.exit(1)

    fn(*args) if args else fn()
