"""
Runbook Executor

Simulates executing READ_ONLY diagnostic steps and returns results
that feed back into the reasoning loop.

In production, this would SSH/kubectl exec real commands.
In stub mode, generates realistic diagnostic output per incident type.
"""
import os, re
from datetime import datetime, timezone


def execute_step(step: dict, incident_type: str = None) -> dict:
    """
    Execute a READ_ONLY diagnostic step.
    Returns structured result with command output.
    """
    action = step["action"]
    step_num = step["step"]

    if os.getenv("RUNBOOK_MODE") == "live":
        return _live_execute(action)

    return _stub_execute(action, incident_type)


def _live_execute(action: str) -> dict:
    """
    Execute real commands. Only safe READ_ONLY commands allowed.
    Blocked: rm, drop, delete, kill, terminate, restart, scale, deploy.
    """
    import subprocess

    # Extract command from action text (look for backtick-wrapped or common patterns)
    cmd = _extract_command(action)
    if not cmd:
        return {"status": "skipped", "reason": "no executable command found", "action": action}

    # Safety check — block anything destructive
    BLOCKED = ["rm ", "drop ", "delete ", "kill ", "terminate", "restart", "scale ", "deploy", "kubectl apply", "kubectl set"]
    if any(b in cmd.lower() for b in BLOCKED):
        return {"status": "blocked", "reason": f"command contains destructive keyword", "command": cmd}

    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return {
            "status": "executed",
            "command": cmd,
            "stdout": r.stdout[:2000],
            "stderr": r.stderr[:500],
            "exit_code": r.returncode,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "command": cmd}
    except Exception as e:
        return {"status": "error", "command": cmd, "error": str(e)}


def _extract_command(action: str) -> str | None:
    """Try to extract an executable command from the action description."""
    # Look for: command after colon
    if ":" in action:
        after_colon = action.split(":", 1)[1].strip()
        # If it looks like a command (starts with common tools)
        tools = ["SELECT", "kubectl", "curl", "dig", "openssl", "df", "du", "find", "cat", "grep", "top", "ps"]
        if any(after_colon.startswith(t) for t in tools):
            return after_colon
    return None


def _stub_execute(action: str, incident_type: str = None) -> dict:
    """Generate realistic diagnostic output based on the action and incident type."""
    action_lower = action.lower()

    # DB diagnostics
    if "pg_stat_activity" in action or "active connections" in action_lower:
        return {
            "status": "executed",
            "command": "SELECT count(*), state FROM pg_stat_activity GROUP BY state",
            "output": "active: 50\nidle: 0\nidle in transaction: 3\ntotal: 53",
            "finding": "All 50 pool connections active, 0 idle — pool fully saturated",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    if "long-running" in action_lower or "blocking" in action_lower:
        return {
            "status": "executed",
            "command": "SELECT pid, now()-query_start AS duration, query FROM pg_stat_activity WHERE state='active' ORDER BY duration DESC LIMIT 5",
            "output": "pid=2341 | duration=47s | SELECT * FROM orders JOIN inventory ON...\npid=2342 | duration=12s | UPDATE payments SET status='pending'...\npid=2343 | duration=3s | SELECT count(*) FROM users",
            "finding": "PID 2341 running for 47s — likely the blocker (full table scan on orders×inventory)",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    # K8s diagnostics
    if "kubectl get pods" in action_lower or "pod status" in action_lower:
        return {
            "status": "executed",
            "command": "kubectl get pods -l app=auth-svc",
            "output": "NAME                       READY   STATUS             RESTARTS   AGE\nauth-svc-7d9f-abc12   0/1     CrashLoopBackOff   7          12m\nauth-svc-7d9f-def34   1/1     Running            0          2h\nauth-svc-7d9f-ghi56   1/1     Running            0          2h",
            "finding": "1/3 pods in CrashLoopBackOff with 7 restarts in 12 minutes",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    if "describe pod" in action_lower or "oom" in action_lower:
        return {
            "status": "executed",
            "command": "kubectl describe pod auth-svc-7d9f-abc12 | grep -A5 'Last State'",
            "output": "Last State: Terminated\n  Reason: OOMKilled\n  Exit Code: 137\n  Started: Mon, 01 Jun 2026 11:45:00 UTC\n  Finished: Mon, 01 Jun 2026 11:47:23 UTC",
            "finding": "Pod terminated by OOMKiller (exit 137) — memory limit exceeded",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    # Network diagnostics
    if "vpc flow" in action_lower or "packet" in action_lower:
        return {
            "status": "executed",
            "command": "aws ec2 describe-flow-logs --filter Name=log-status,Values=ACTIVE",
            "output": "subnet-az-b: 18.2% packet loss (REJECT actions: 4,231/min)\nsubnet-az-a: 0.01% packet loss (normal)\nsubnet-az-c: 0.02% packet loss (normal)",
            "finding": "AZ-b showing 18.2% packet loss — significantly above baseline",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    if "target group" in action_lower or "health" in action_lower:
        return {
            "status": "executed",
            "command": "aws elbv2 describe-target-health --target-group-arn tg-api-az-b",
            "output": "tg-api-az-b: 0/3 healthy (all draining)\ntg-api-az-a: 3/3 healthy\ntg-api-az-c: 3/3 healthy",
            "finding": "All targets in AZ-b are draining — no healthy instances",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    # Disk diagnostics
    if "df" in action_lower:
        return {
            "status": "executed",
            "command": "df -h",
            "output": "/dev/xvda1  100G  99G  1G  99% /\n/dev/xvdb   500G  498G  2G  100% /data",
            "finding": "/data partition at 100% — immediate action needed",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    # DNS diagnostics
    if "dig" in action_lower or "dns" in action_lower or "coredns" in action_lower:
        return {
            "status": "executed",
            "command": "kubectl get pods -n kube-system -l k8s-app=kube-dns",
            "output": "NAME                      READY   STATUS    RESTARTS\ncoredns-5d78c9869d-abc   0/1     Error     3\ncoredns-5d78c9869d-def   1/1     Running   0",
            "finding": "1/2 CoreDNS pods in Error state — DNS resolution degraded",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    # TLS diagnostics
    if "openssl" in action_lower or "cert" in action_lower:
        return {
            "status": "executed",
            "command": "openssl s_client -connect api.example.com:443 | openssl x509 -noout -dates",
            "output": "notBefore=Jan 15 00:00:00 2025 GMT\nnotAfter=Jan 14 23:59:59 2026 GMT",
            "finding": "Certificate expired 5 months ago — all HTTPS connections failing",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    # Generic fallback
    return {
        "status": "executed",
        "command": f"(diagnostic for: {action[:50]})",
        "output": "Check completed — see findings",
        "finding": "Diagnostic executed successfully",
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
