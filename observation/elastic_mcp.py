"""
Elastic MCP Integration

Mirrors the 4 MCP tools from the README architecture:
  - log_query:         fetch recent errors by service/time
  - trace_correlation: link request traces across microservices
  - metrics_tool:      detect latency, CPU, volume anomalies
  - search_tool:       semantic + keyword log search

Set ELASTIC_MCP_URL to connect to a real MCP server.
Falls back to stub data when not configured or on connection failure.
"""
import os
from datetime import datetime, timezone


class ElasticMCP:
    """
    Elastic MCP client.
    Set ELASTIC_MCP_URL env var to point at a real MCP server.
    Falls back to stub data when not configured or on failure.
    """

    def __init__(self):
        self.url = os.getenv("ELASTIC_MCP_URL", "").rstrip("/")
        self.live = bool(self.url)
        self.timeout = int(os.getenv("ELASTIC_MCP_TIMEOUT", "10"))

    def query(self, signal: dict) -> dict:
        """Run all four MCP tools against the incident signal."""
        if self.live:
            result = self._live_query(signal)
            # If all tools errored, fall back to stub
            if all("error" in v for k, v in result.items() if k not in ("signals_used", "queried_at", "mode")):
                stub = self._stub_query(signal)
                stub["mode"] = "stub_fallback"
                stub["live_errors"] = {k: v["error"] for k, v in result.items() if isinstance(v, dict) and "error" in v}
                return stub
            return result
        return self._stub_query(signal)

    def health(self) -> dict:
        """Check if the MCP server is reachable."""
        if not self.live:
            return {"status": "stub", "url": None}
        import httpx
        try:
            r = httpx.get(f"{self.url}/health", timeout=5)
            return {"status": "ok" if r.status_code == 200 else "degraded", "url": self.url, "code": r.status_code}
        except Exception as e:
            return {"status": "unreachable", "url": self.url, "error": str(e)}

    # ── Live (real MCP server) ────────────────────────────────────────────────

    def _live_query(self, signal: dict) -> dict:
        """Calls the real Elastic MCP server with per-tool error isolation."""
        import httpx
        services = signal.get("services", [])
        error_msgs = " ".join(e["msg"] for e in signal.get("error_logs", [])[:3])
        results = {}

        tools = [
            ("log_query",         {"services": services, "window_min": 15, "level": "ERROR"}),
            ("trace_correlation", {"services": services}),
            ("metrics_tool",      {"services": services, "window_min": 30}),
            ("search_tool",       {"query": error_msgs}),
        ]

        with httpx.Client(base_url=self.url, timeout=self.timeout) as client:
            for tool, payload in tools:
                try:
                    r = client.post(f"/tools/{tool}", json=payload)
                    r.raise_for_status()
                    results[tool] = r.json()
                except httpx.TimeoutException:
                    results[tool] = {"error": "timeout", "tool": tool}
                except httpx.HTTPStatusError as e:
                    results[tool] = {"error": f"HTTP {e.response.status_code}", "tool": tool}
                except Exception as e:
                    results[tool] = {"error": str(e), "tool": tool}

        results["signals_used"] = [k for k in results if "error" not in results[k]]
        results["queried_at"] = datetime.now(timezone.utc).isoformat()
        results["mode"] = "live"
        return results

    # ── Stub (offline / demo) ─────────────────────────────────────────────────

    def _stub_query(self, signal: dict) -> dict:
        services = signal.get("services", [])
        errors = signal.get("error_logs", [])
        signal_count = signal.get("signal_count", 0)

        error_rate = signal_count * 12
        latency_p99 = 180 + signal_count * 280

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
