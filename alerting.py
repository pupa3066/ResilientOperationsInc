"""
Severity-Based Alerting & Escalation

Routes incidents by severity:
  P0 (≥90% confidence): immediate escalation, auto-page on-call
  P1 (≥70%): 5-minute SLA, notify channel
  P2 (<70%): informational, log only

Notification hooks are pluggable (Slack, PagerDuty, email stubs).
"""
import os, json
from datetime import datetime, timezone
from pathlib import Path

_ALERT_LOG = Path(__file__).parent / "alerts.jsonl"

# SLA in seconds per severity
SLA = {"P0": 0, "P1": 300, "P2": 3600}


def classify_severity(confidence_pct: int) -> str:
    if confidence_pct >= 90:
        return "P0"
    if confidence_pct >= 70:
        return "P1"
    return "P2"


def alert(incident: dict) -> dict:
    """
    Generate alert based on incident severity.
    Returns alert record with routing decision.
    """
    reasoning = incident.get("reasoning", {})
    confidence = reasoning.get("confidence_pct", 0)
    severity = classify_severity(confidence)
    title = reasoning.get("incident_title", "Unknown")

    record = {
        "incident_id": incident["id"],
        "severity": severity,
        "title": title,
        "confidence_pct": confidence,
        "sla_seconds": SLA[severity],
        "blast_radius": reasoning.get("blast_radius", []),
        "routing": _route(severity),
        "alerted_at": datetime.now(timezone.utc).isoformat(),
    }

    # Persist
    with open(_ALERT_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")

    # Execute notification
    _notify(record)
    return record


def _route(severity: str) -> dict:
    """Determine notification routing based on severity."""
    if severity == "P0":
        return {
            "channels": ["pagerduty", "slack-incidents", "sre-oncall"],
            "escalation": "immediate",
            "auto_page": True,
        }
    if severity == "P1":
        return {
            "channels": ["slack-incidents", "sre-oncall"],
            "escalation": "5min",
            "auto_page": False,
        }
    return {
        "channels": ["slack-alerts"],
        "escalation": "none",
        "auto_page": False,
    }


def _notify(record: dict):
    """
    Send notifications. In production, replace with real integrations.
    Respects ALERT_MODE env var: 'live' for real calls, default is log-only.
    """
    severity = record["severity"]
    title = record["title"]
    routing = record["routing"]

    if os.getenv("ALERT_MODE") == "live":
        # Production hooks would go here:
        # _pagerduty_trigger(record) if routing["auto_page"]
        # _slack_post(channel, record) for channel in routing["channels"]
        pass

    # Always print for visibility
    icons = {"P0": "🚨", "P1": "⚠️", "P2": "ℹ️"}
    print(f"[alerting] {icons.get(severity, '?')} {severity} | {title} → {routing['channels']}")


def get_alerts() -> list[dict]:
    """Load all alert records."""
    if not _ALERT_LOG.exists():
        return []
    return [json.loads(line) for line in _ALERT_LOG.read_text().splitlines() if line.strip()]


def pending_escalations() -> list[dict]:
    """Find alerts that have breached their SLA without resolution."""
    alerts = get_alerts()
    now = datetime.now(timezone.utc)
    pending = []
    for a in alerts:
        alerted = datetime.fromisoformat(a["alerted_at"])
        elapsed = (now - alerted).total_seconds()
        if elapsed > a["sla_seconds"] and a["severity"] in ("P0", "P1"):
            a["sla_breached_seconds"] = elapsed - a["sla_seconds"]
            pending.append(a)
    return pending
