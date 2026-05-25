"""
Elastic MCP Stub Integration

Simulates the Elastic MCP server interface used in the README architecture.
In production, replace _stub_query() with real MCP tool calls.

Tools mirrored from README:
  - log_query:         fetch recent errors by service/time
  - trace_correlation: link request traces across microservices
  - metrics_tool:      detect latency, CPU, volume anomalies
  - search_tool:       semantic + keyword log search
"""
import os
from datetime import datetime, timezone


class ElasticMCP:
    """
    Elastic MCP client.
    Set ELASTIC_MCP_URL env var to point at a real MCP server.
    Falls back to stub data when not configured.
    """

    def __init__(self):
        self.url = os.getenv("ELASTIC_MCP_URL")
        self.live = bool(self.url)

    def query(self, signal: dict) -> dict:
        """Run all four MCP tools against the incident signal."""
        if self.live:
            return self._live_query(signal)
        return self._stub_query(signal)

    # ── Live (real MCP server) ────────────────────────────────────────────────

    def _live_query(self, signal: dict) -> dict:
        """
        Calls the real Elastic MCP server.
        Expects MCP tool responses in standard JSON format.
        """
        import httpx
        services = signal.get("services", [])
        results = {}
        with httpx.Client(base_url=self.url, timeout=10) as client:
            for tool, payload in [
                ("log_query",         {"services": services, "window_min": 15, "level": "ERROR"}),
                ("trace_correlation", {"services": services}),
                ("metrics_tool",      {"services": services, "window_min": 30}),
                ("search_tool",       {"query": " ".join(e["msg"] for e in signal.get("error_logs", [])[:3])}),
            ]:
                try:
                    r = client.post(f"/tools/{tool}", json=payload)
                    r.raise_for_status()
                    results[tool] = r.json()
                except Exception as exc:
                    results[tool] = {"error": str(exc)}
        results["signals_used"] = list(results.keys())
        results["queried_at"] = datetime.now(timezone.utc).isoformat()
        return results

    # ── Stub (offline / demo) ─────────────────────────────────────────────────

    def _stub_query(self, signal: dict) -> dict:
        services = signal.get("services", [])
        errors = signal.get("error_logs", [])
        signal_count = signal.get("signal_count", 0)

        # Derive stub metrics from actual log content
        error_rate = signal_count * 12          # ~errors/min estimate
        latency_p99 = 180 + signal_count * 280  # baseline 180ms + degradation

        return {
            "log_query": {
                "tool": "log_query",
                "window": "last 15 min",
                "services": services,
                "error_count": signal_count,
                "sample_errors": [e["msg"] for e in errors[:3]],
            },
            "trace_correlation": {
                "tool": "trace_correlation",
                "services": services,
                "cascade_detected": len(signal.get("cascade_candidates", [])) > 0,
                "shared_services": [
                    c["shared_services"]
                    for c in signal.get("cascade_candidates", [])
                ],
            },
            "metrics_tool": {
                "tool": "metrics_tool",
                "error_rate_per_min": error_rate,
                "latency_p99_ms": latency_p99,
                "anomaly_detected": signal_count >= 5,
            },
            "search_tool": {
                "tool": "search_tool",
                "query": " ".join(e["msg"] for e in errors[:2]),
                "hits": signal_count,
                "top_services": services[:3],
            },
            "signals_used": ["log_query", "trace_correlation", "metrics_tool", "search_tool"],
            "queried_at": datetime.now(timezone.utc).isoformat(),
            "mode": "stub",
        }
