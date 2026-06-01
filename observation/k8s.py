"""
Kubernetes Observation Module

Queries pod status, deployments, and events for incident context.
Set K8S_MODE=live to use real kubectl/k8s API (requires kubeconfig).
Falls back to stub data for demo/offline use.

Provides:
  - pod_status:   pod health, restarts, OOM kills
  - deployments:  rollout status, replica counts
  - events:       recent warning/error events for affected services
"""
import os, json, subprocess
from datetime import datetime, timezone


class K8sObserver:
    def __init__(self):
        self.live = os.getenv("K8S_MODE") == "live"
        self.namespace = os.getenv("K8S_NAMESPACE", "default")

    def query(self, services: list[str]) -> dict:
        """Get k8s context for the given services."""
        if self.live:
            return self._live_query(services)
        return self._stub_query(services)

    def health(self) -> dict:
        if not self.live:
            return {"status": "stub", "namespace": self.namespace}
        try:
            r = subprocess.run(
                ["kubectl", "cluster-info", "--request-timeout=5s"],
                capture_output=True, text=True, timeout=10
            )
            return {"status": "ok" if r.returncode == 0 else "error", "namespace": self.namespace}
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    def _live_query(self, services: list[str]) -> dict:
        results = {
            "pod_status": self._kubectl_pods(services),
            "deployments": self._kubectl_deployments(services),
            "events": self._kubectl_events(services),
            "queried_at": datetime.now(timezone.utc).isoformat(),
            "mode": "live",
        }
        return results

    def _kubectl_pods(self, services: list[str]) -> list[dict]:
        pods = []
        for svc in services:
            try:
                r = subprocess.run(
                    ["kubectl", "get", "pods", "-n", self.namespace,
                     "-l", f"app={svc}", "-o", "json", "--request-timeout=5s"],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode == 0:
                    data = json.loads(r.stdout)
                    for item in data.get("items", []):
                        status = item.get("status", {})
                        containers = status.get("containerStatuses", [{}])
                        pods.append({
                            "name": item["metadata"]["name"],
                            "service": svc,
                            "phase": status.get("phase"),
                            "restarts": sum(c.get("restartCount", 0) for c in containers),
                            "ready": all(c.get("ready", False) for c in containers),
                        })
            except Exception:
                pods.append({"service": svc, "error": "kubectl failed"})
        return pods

    def _kubectl_deployments(self, services: list[str]) -> list[dict]:
        deps = []
        for svc in services:
            try:
                r = subprocess.run(
                    ["kubectl", "get", "deployment", svc, "-n", self.namespace,
                     "-o", "json", "--request-timeout=5s"],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode == 0:
                    data = json.loads(r.stdout)
                    spec = data.get("spec", {})
                    status = data.get("status", {})
                    deps.append({
                        "name": svc,
                        "replicas": spec.get("replicas"),
                        "ready": status.get("readyReplicas", 0),
                        "updated": status.get("updatedReplicas", 0),
                        "available": status.get("availableReplicas", 0),
                    })
            except Exception:
                deps.append({"name": svc, "error": "kubectl failed"})
        return deps

    def _kubectl_events(self, services: list[str]) -> list[dict]:
        try:
            r = subprocess.run(
                ["kubectl", "get", "events", "-n", self.namespace,
                 "--field-selector=type!=Normal", "-o", "json", "--request-timeout=5s"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode != 0:
                return [{"error": "kubectl events failed"}]
            data = json.loads(r.stdout)
            events = []
            for item in data.get("items", [])[-20:]:
                obj = item.get("involvedObject", {})
                events.append({
                    "reason": item.get("reason"),
                    "message": item.get("message"),
                    "kind": obj.get("kind"),
                    "name": obj.get("name"),
                    "count": item.get("count"),
                    "last_seen": item.get("lastTimestamp"),
                })
            return events
        except Exception as e:
            return [{"error": str(e)}]

    def _stub_query(self, services: list[str]) -> dict:
        """Generate realistic stub k8s data based on service names."""
        pods = []
        deployments = []
        events = []

        for svc in services:
            # Simulate 2-3 pods per service
            for i in range(2):
                pod_name = f"{svc}-{hex(hash(svc + str(i)))[-8:]}"
                is_unhealthy = i == 0 and svc == services[0]
                pods.append({
                    "name": pod_name,
                    "service": svc,
                    "phase": "CrashLoopBackOff" if is_unhealthy else "Running",
                    "restarts": 7 if is_unhealthy else 0,
                    "ready": not is_unhealthy,
                })

            deployments.append({
                "name": svc,
                "replicas": 3,
                "ready": 2 if svc == services[0] else 3,
                "updated": 3,
                "available": 2 if svc == services[0] else 3,
            })

        # Stub warning events
        events = [
            {"reason": "BackOff", "message": f"Back-off restarting failed container in pod {services[0]}-abc123", "kind": "Pod", "name": f"{services[0]}-abc123", "count": 7, "last_seen": datetime.now(timezone.utc).isoformat()},
            {"reason": "Unhealthy", "message": "Readiness probe failed: connection refused", "kind": "Pod", "name": f"{services[0]}-abc123", "count": 12, "last_seen": datetime.now(timezone.utc).isoformat()},
        ]

        return {
            "pod_status": pods,
            "deployments": deployments,
            "events": events,
            "queried_at": datetime.now(timezone.utc).isoformat(),
            "mode": "stub",
        }
