"""
Incident Timeline

Tracks every state transition, agent action, and decision with timestamps.
Produces a structured timeline for post-mortem analysis.
"""
from datetime import datetime, timezone


class Timeline:
    """Per-incident timeline tracker."""

    def __init__(self, incident_id: str):
        self.incident_id = incident_id
        self.events: list[dict] = []
        self._t0 = datetime.now(timezone.utc)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _elapsed(self) -> float:
        return (datetime.now(timezone.utc) - self._t0).total_seconds()

    def record(self, event_type: str, detail: str, metadata: dict = None):
        self.events.append({
            "t": self._now(),
            "elapsed_s": round(self._elapsed(), 2),
            "type": event_type,
            "detail": detail,
            "metadata": metadata or {},
        })

    # Convenience methods for common SRE events
    def detected(self, source: str, signal_count: int):
        self.record("detected", f"Incident detected from {source}", {"signal_count": signal_count})

    def reasoning_start(self):
        self.record("reasoning_start", "Reasoning agent analyzing signals")

    def reasoning_complete(self, title: str, confidence: int, root_cause: str):
        self.record("reasoning_complete", f"{title} ({confidence}%)", {"root_cause": root_cause, "confidence_pct": confidence})

    def plan_generated(self, step_count: int, mutating_count: int):
        self.record("plan_generated", f"{step_count} steps ({mutating_count} require approval)")

    def step_auto_executed(self, step: int, action: str, result: dict = None):
        self.record("step_executed", f"Step {step} auto-executed: {action[:60]}", {"step": step, "result": result})

    def step_awaiting_approval(self, step: int, action: str, risk: str):
        self.record("awaiting_approval", f"Step {step} [{risk}]: {action[:60]}", {"step": step, "risk": risk})

    def step_approved(self, step: int, action: str):
        self.record("step_approved", f"Step {step} approved: {action[:60]}", {"step": step})

    def step_rejected(self, step: int, action: str):
        self.record("step_rejected", f"Step {step} rejected: {action[:60]}", {"step": step})

    def step_blocked(self, step: int, blocked_by: int):
        self.record("step_blocked", f"Step {step} blocked by rejected step {blocked_by}", {"step": step, "blocked_by": blocked_by})

    def escalated(self, severity: str, channels: list[str]):
        self.record("escalated", f"{severity} alert sent to {channels}", {"severity": severity})

    def resolved(self, status: str):
        self.record("resolved", f"Incident {status}", {"final_status": status, "total_duration_s": round(self._elapsed(), 2)})

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "started_at": self._t0.isoformat(),
            "duration_s": round(self._elapsed(), 2),
            "event_count": len(self.events),
            "events": self.events,
        }

    def summary(self) -> str:
        """One-line summary for logging."""
        duration = self._elapsed()
        return f"[{self.incident_id}] {len(self.events)} events in {duration:.1f}s"
