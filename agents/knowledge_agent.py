"""
KnowledgeAgent — RFC/Runbook lookup + similar past incident retrieval.

Given a classified incident type, returns:
  - relevant_rfcs:    IETF/industry RFCs that govern the affected protocol/system
  - runbooks:         step-by-step operational runbooks for this incident type
  - similar_incidents: past incidents of the same type with outcomes
  - recommended_approach: synthesized recommendation based on all sources

In production, `similar_incidents` would query a vector DB (e.g. Elastic,
Pinecone) over your historical incident corpus. Here we use a curated
representative set per incident type.
"""

# ── RFC + Runbook knowledge base ──────────────────────────────────────────────

_KNOWLEDGE: dict[str, dict] = {
    "db_pool": {
        "rfcs": [
            {"id": "RFC 9110", "title": "HTTP Semantics — 503 Service Unavailable", "relevance": "Correct 503 signaling when DB is unavailable"},
            {"id": "JDBC Spec 4.3", "title": "Java Database Connectivity — Connection Pooling", "relevance": "Pool sizing, timeout, and validation query best practices"},
            {"id": "PostgreSQL Docs: pg_stat_activity", "title": "PostgreSQL Connection Management", "relevance": "Identifying and terminating blocking queries"},
        ],
        "runbooks": [
            {
                "title": "DB Connection Pool Exhaustion Runbook",
                "steps": [
                    "1. SELECT count(*), state FROM pg_stat_activity GROUP BY state — check active vs idle",
                    "2. SELECT pid, now()-query_start AS duration, query FROM pg_stat_activity WHERE state='active' ORDER BY duration DESC LIMIT 5",
                    "3. Kill blocker: SELECT pg_terminate_backend(<pid>)",
                    "4. Increase pool: set spring.datasource.hikari.maximum-pool-size=100",
                    "5. Add statement_timeout='30s' in postgres.conf",
                    "6. Monitor: watch -n2 'psql -c \"SELECT count(*) FROM pg_stat_activity\"'",
                ],
                "prevention": "Set connection pool size = (core_count * 2) + effective_spindle_count per PgBouncer guidelines",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2024-0891", "title": "Payment service pool exhaustion during Black Friday", "resolution": "Killed 3 long-running analytics queries, increased pool 50→150, added read replica", "mttr_min": 18, "outcome": "RESOLVED"},
            {"id": "INC-2023-1102", "title": "Order DB pool exhausted after ORM N+1 query regression", "resolution": "Rolled back ORM migration, added query timeout, fixed N+1 with eager loading", "mttr_min": 34, "outcome": "RESOLVED"},
        ],
    },

    "network": {
        "rfcs": [
            {"id": "RFC 4271", "title": "BGP-4 — Border Gateway Protocol", "relevance": "BGP route flap detection and recovery procedures"},
            {"id": "RFC 5681", "title": "TCP Congestion Control", "relevance": "Packet loss impact on TCP throughput and retransmission behavior"},
            {"id": "RFC 7011", "title": "IPFIX — IP Flow Information Export", "relevance": "Flow-level packet loss measurement and reporting"},
            {"id": "AWS Well-Architected: Reliability Pillar", "title": "Multi-AZ Design", "relevance": "AZ failover patterns and traffic rerouting"},
        ],
        "runbooks": [
            {
                "title": "AZ Network Degradation Runbook",
                "steps": [
                    "1. Check VPC Flow Logs: filter for REJECT actions in affected subnet",
                    "2. aws ec2 describe-network-interfaces --filters Name=subnet-id,Values=<subnet>",
                    "3. Reroute ALB: aws elbv2 modify-load-balancer-attributes (disable AZ-b)",
                    "4. Scale replicas in healthy AZs: aws rds modify-db-cluster --availability-zones us-east-1a us-east-1c",
                    "5. Update Lambda VPC config: aws lambda update-function-configuration --vpc-config SubnetIds=<az-a,az-c>",
                    "6. Open AWS support case: P1 — Network degradation in <AZ>",
                ],
                "prevention": "Deploy across ≥3 AZs, use ALB with cross-zone load balancing, test AZ failover quarterly",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2024-0312", "title": "AWS us-east-1 AZ-b packet loss (real AWS outage)", "resolution": "Rerouted to AZ-a/c, scaled RDS replicas, AWS resolved underlying hardware issue in 4h", "mttr_min": 13, "outcome": "RESOLVED"},
            {"id": "INC-2023-0719", "title": "GCP us-central1-b network partition", "resolution": "Failover to us-central1-a/c via traffic director, restored in 22 min", "mttr_min": 22, "outcome": "RESOLVED"},
        ],
    },

    "oom": {
        "rfcs": [
            {"id": "Linux OOM Killer Docs", "title": "Linux Out-of-Memory Killer", "relevance": "OOM score tuning, oom_score_adj, cgroup memory limits"},
            {"id": "JVM Tuning Guide (OpenJDK)", "title": "Java Heap and GC Tuning", "relevance": "-Xmx, -Xms, G1GC tuning, heap dump analysis"},
            {"id": "Kubernetes Resource Management", "title": "K8s requests/limits best practices", "relevance": "Setting memory requests = limits to avoid OOM eviction"},
        ],
        "runbooks": [
            {
                "title": "OOM Kill / CrashLoopBackOff Runbook",
                "steps": [
                    "1. kubectl describe pod <pod> | grep -A5 OOMKilled",
                    "2. kubectl top pod <pod> --containers — check memory usage trend",
                    "3. Edit deployment: kubectl set resources deployment/<name> --limits=memory=1Gi",
                    "4. kubectl apply -f deployment.yaml && kubectl rollout status",
                    "5. Capture heap dump: kubectl exec <pod> -- jcmd <pid> GC.heap_dump /tmp/heap.hprof",
                    "6. Analyze with Eclipse MAT or VisualVM",
                ],
                "prevention": "Set memory request = 70% of limit, add -XX:+HeapDumpOnOutOfMemoryError, alert at 85% usage",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2025-0203", "title": "auth-svc OOM after JWT cache unbounded growth", "resolution": "Increased limit to 1Gi, added LRU eviction to JWT cache (max 10k entries)", "mttr_min": 11, "outcome": "RESOLVED"},
            {"id": "INC-2024-1115", "title": "ML inference service OOM on large batch", "resolution": "Added batch size limit, increased pod memory to 4Gi, added HPA", "mttr_min": 25, "outcome": "RESOLVED"},
        ],
    },

    "disk_full": {
        "rfcs": [
            {"id": "POSIX IEEE 1003.1", "title": "POSIX Filesystem — ENOSPC error handling", "relevance": "Correct ENOSPC handling and graceful degradation"},
            {"id": "Linux logrotate(8)", "title": "Log Rotation Best Practices", "relevance": "Automated log rotation configuration"},
        ],
        "runbooks": [
            {
                "title": "Disk Full (ENOSPC) Runbook",
                "steps": [
                    "1. df -h — identify full partition",
                    "2. du -sh /* 2>/dev/null | sort -rh | head -10 — find largest dirs",
                    "3. find /var/log -name '*.log' -size +100M — find large log files",
                    "4. journalctl --vacuum-size=500M — trim systemd journal",
                    "5. docker system prune -f — remove unused Docker layers",
                    "6. AWS: aws ec2 modify-volume --size <new-size> then resize2fs /dev/<device>",
                ],
                "prevention": "Alert at 80% disk usage, enforce log retention ≤7 days, use EBS auto-scaling",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2025-0118", "title": "Postgres WAL filled /data partition", "resolution": "Archived WAL to S3, expanded EBS 100GB→500GB, set wal_keep_size=1GB", "mttr_min": 28, "outcome": "RESOLVED"},
        ],
    },

    "cpu_throttle": {
        "rfcs": [
            {"id": "Linux CFS Bandwidth Control", "title": "Completely Fair Scheduler CPU Throttling", "relevance": "Understanding cpu.cfs_quota_us and throttling behavior"},
            {"id": "Kubernetes CPU Management", "title": "K8s CPU requests/limits and QoS classes", "relevance": "Guaranteed vs Burstable QoS, CPU pinning"},
        ],
        "runbooks": [
            {
                "title": "CPU Throttling Runbook",
                "steps": [
                    "1. kubectl top pods --sort-by=cpu — identify hot pods",
                    "2. cat /sys/fs/cgroup/cpu/cpu.stat | grep throttled — confirm throttling",
                    "3. kubectl set resources deployment/<name> --requests=cpu=500m --limits=cpu=2000m",
                    "4. kubectl scale deployment/<name> --replicas=<N> — horizontal scale",
                    "5. Profile: kubectl exec <pod> -- py-spy top --pid <pid> (Python) or async-profiler (JVM)",
                ],
                "prevention": "Set CPU request = average usage, limit = 3x request, use HPA on CPU metric",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2024-0822", "title": "Report generation service CPU throttled during month-end", "resolution": "Moved report jobs to dedicated node pool, increased CPU limit 500m→4000m", "mttr_min": 15, "outcome": "RESOLVED"},
        ],
    },

    "tls_cert": {
        "rfcs": [
            {"id": "RFC 8446", "title": "TLS 1.3", "relevance": "TLS handshake failure modes and certificate validation"},
            {"id": "RFC 5280", "title": "X.509 PKI Certificate and CRL Profile", "relevance": "Certificate validity period, chain validation, revocation"},
            {"id": "RFC 8555", "title": "ACME — Automatic Certificate Management Environment", "relevance": "Let's Encrypt / cert-manager automated renewal"},
        ],
        "runbooks": [
            {
                "title": "TLS Certificate Expiry Runbook",
                "steps": [
                    "1. openssl s_client -connect <host>:443 -servername <host> 2>/dev/null | openssl x509 -noout -dates",
                    "2. Check cert-manager: kubectl get certificates -A",
                    "3. Force renewal: kubectl delete secret <tls-secret> (cert-manager will recreate)",
                    "4. Let's Encrypt: certbot renew --force-renewal",
                    "5. Verify: curl -vI https://<host> 2>&1 | grep -E 'expire|issuer|subject'",
                ],
                "prevention": "Alert 30 days before expiry, use cert-manager with auto-renewal, never use manual certs in prod",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2024-0401", "title": "Wildcard cert expired — all HTTPS endpoints down", "resolution": "Emergency cert renewal via Let's Encrypt, deployed in 8 min, added 30-day expiry alert", "mttr_min": 8, "outcome": "RESOLVED"},
        ],
    },

    "deploy_rollout": {
        "rfcs": [
            {"id": "Kubernetes Deployment Docs", "title": "Rolling Update Strategy", "relevance": "maxSurge, maxUnavailable, readiness probe configuration"},
            {"id": "SRE Book: Chapter 8", "title": "Release Engineering", "relevance": "Canary deployments, progressive rollouts, rollback triggers"},
        ],
        "runbooks": [
            {
                "title": "Failed Deployment Runbook",
                "steps": [
                    "1. kubectl rollout status deployment/<name> — check stuck rollout",
                    "2. kubectl describe pod <new-pod> — read Events section for probe failures",
                    "3. kubectl logs <new-pod> --previous — crash logs from last container",
                    "4. ROLLBACK: kubectl rollout undo deployment/<name>",
                    "5. kubectl rollout history deployment/<name> — list revisions",
                    "6. Fix: update image tag, resource limits, or probe config then re-deploy",
                ],
                "prevention": "Use canary deployments (5% traffic first), set readiness probe with initialDelaySeconds≥30",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2025-0309", "title": "New API version CrashLoopBackOff — missing env var", "resolution": "Rolled back in 3 min, added missing SECRET_KEY env var, redeployed", "mttr_min": 7, "outcome": "RESOLVED"},
        ],
    },

    "dns": {
        "rfcs": [
            {"id": "RFC 1034", "title": "DNS Concepts and Facilities", "relevance": "DNS resolution chain, TTL, negative caching"},
            {"id": "RFC 1035", "title": "DNS Implementation and Specification", "relevance": "Query/response format, NXDOMAIN handling"},
            {"id": "RFC 8767", "title": "Serving Stale Data to Improve DNS Resiliency", "relevance": "Stale-while-revalidate for DNS outage tolerance"},
        ],
        "runbooks": [
            {
                "title": "DNS Resolution Failure Runbook",
                "steps": [
                    "1. kubectl get pods -n kube-system | grep coredns — check CoreDNS health",
                    "2. kubectl exec <any-pod> -- nslookup kubernetes.default — test internal DNS",
                    "3. kubectl logs -n kube-system -l k8s-app=kube-dns --tail=50",
                    "4. kubectl rollout restart deployment/coredns -n kube-system",
                    "5. Check ConfigMap: kubectl get configmap coredns -n kube-system -o yaml",
                    "6. Verify upstream: dig @8.8.8.8 <external-domain> from a pod",
                ],
                "prevention": "Run ≥2 CoreDNS replicas, set ndots:2 in pod DNS config, use NodeLocal DNSCache",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2024-0614", "title": "CoreDNS OOMKilled — all service discovery broken", "resolution": "Increased CoreDNS memory limit 170Mi→512Mi, restarted pods, restored in 6 min", "mttr_min": 6, "outcome": "RESOLVED"},
        ],
    },

    "rate_limit": {
        "rfcs": [
            {"id": "RFC 6585", "title": "HTTP 429 Too Many Requests", "relevance": "Correct 429 response format, Retry-After header usage"},
            {"id": "RFC 8631", "title": "Link Relation Types for Web Services", "relevance": "Rate limit headers: X-RateLimit-Limit, X-RateLimit-Remaining"},
            {"id": "Token Bucket Algorithm (Tanenbaum)", "title": "Token Bucket Rate Limiting", "relevance": "Client-side rate limiter implementation"},
        ],
        "runbooks": [
            {
                "title": "Rate Limit / 429 Runbook",
                "steps": [
                    "1. Check response headers: curl -I <endpoint> | grep -i 'ratelimit\\|retry-after'",
                    "2. Identify which client/service is over-calling",
                    "3. Implement exponential backoff: base=1s, max=60s, jitter=random(0,1)*base",
                    "4. Add client-side token bucket (e.g. ratelimiter library)",
                    "5. Request quota increase from upstream (AWS, Stripe, etc.)",
                    "6. Cache GET responses to reduce call volume",
                ],
                "prevention": "Always implement retry with exponential backoff + jitter, cache aggressively, monitor quota usage",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2024-1203", "title": "Stripe API 429 storm during payment retry loop", "resolution": "Added exponential backoff, reduced retry attempts 10→3, added idempotency keys", "mttr_min": 20, "outcome": "RESOLVED"},
        ],
    },

    "cascade_timeout": {
        "rfcs": [
            {"id": "RFC 7807", "title": "Problem Details for HTTP APIs", "relevance": "Structured error responses for timeout/cascade failures"},
            {"id": "Hystrix / Resilience4j Docs", "title": "Circuit Breaker Pattern", "relevance": "Circuit breaker states: CLOSED→OPEN→HALF_OPEN, threshold tuning"},
            {"id": "SRE Book: Chapter 21", "title": "Handling Overload", "relevance": "Load shedding, backpressure, bulkhead patterns"},
        ],
        "runbooks": [
            {
                "title": "Cascading Timeout / Circuit Breaker Runbook",
                "steps": [
                    "1. GET /actuator/circuitbreakers — identify OPEN circuits",
                    "2. Distributed trace: find the root slow service (highest latency leaf node)",
                    "3. Manually force circuit OPEN on root service to shed load",
                    "4. Check thread pool saturation: GET /actuator/metrics/executor.active",
                    "5. Reduce timeout on root service calls to 2s to fail fast",
                    "6. Once root service recovers, reset circuit: POST /actuator/circuitbreakers/<name>/reset",
                ],
                "prevention": "Set timeouts on ALL inter-service calls, use bulkhead per dependency, test circuit breaker quarterly",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2024-0509", "title": "Inventory service slowdown cascaded to 8 downstream services", "resolution": "Opened circuit breakers, shed load, fixed N+1 DB query in inventory-svc", "mttr_min": 31, "outcome": "RESOLVED"},
        ],
    },

    "data_corruption": {
        "rfcs": [
            {"id": "RFC 1321", "title": "MD5 Message-Digest Algorithm", "relevance": "Checksum verification for data integrity (use SHA-256 in practice)"},
            {"id": "Apache Avro / Protobuf Schema Evolution", "title": "Schema Evolution Best Practices", "relevance": "Backward/forward compatibility rules for schema changes"},
            {"id": "Kafka Dead Letter Queue Pattern", "title": "DLQ for Corrupt Messages", "relevance": "Isolating corrupt messages without blocking consumers"},
        ],
        "runbooks": [
            {
                "title": "Data Corruption / Deserialization Error Runbook",
                "steps": [
                    "1. Log raw payload before deserialization to identify corrupt record",
                    "2. Move corrupt messages to DLQ: kafka-consumer-groups.sh --reset-offsets",
                    "3. Check schema registry: curl <registry>/subjects/<topic>-value/versions",
                    "4. Compare producer and consumer schema versions",
                    "5. If schema mismatch: rollback consumer or update schema with compatibility",
                    "6. Replay DLQ after fix: kafka-console-consumer.sh --topic <dlq-topic>",
                ],
                "prevention": "Enforce schema registry with BACKWARD_TRANSITIVE compatibility, validate at ingestion boundary",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2023-0827", "title": "Avro schema change broke downstream consumer", "resolution": "Rolled back producer schema, added BACKWARD compatibility check to CI", "mttr_min": 45, "outcome": "RESOLVED"},
        ],
    },

    "auth_failure": {
        "rfcs": [
            {"id": "RFC 6749", "title": "OAuth 2.0 Authorization Framework", "relevance": "Token lifecycle, refresh flow, scope validation"},
            {"id": "RFC 7519", "title": "JSON Web Token (JWT)", "relevance": "JWT claims validation: exp, iss, aud, nbf"},
            {"id": "RFC 7617", "title": "HTTP Basic Authentication", "relevance": "Credential encoding and transmission security"},
            {"id": "RFC 8693", "title": "OAuth 2.0 Token Exchange", "relevance": "Service-to-service token delegation patterns"},
        ],
        "runbooks": [
            {
                "title": "Auth / Token Failure Runbook",
                "steps": [
                    "1. Decode JWT: echo '<token>' | cut -d. -f2 | base64 -d | jq . — check exp claim",
                    "2. curl -I <endpoint> — check WWW-Authenticate header for specific error",
                    "3. kubectl get rolebindings,clusterrolebindings -A | grep <service-account>",
                    "4. Check OIDC provider health: curl <issuer>/.well-known/openid-configuration",
                    "5. Rotate secret: kubectl create secret generic <name> --from-literal=key=<new-val> --dry-run=client -o yaml | kubectl apply -f -",
                    "6. kubectl rollout restart deployment/<name> to pick up new secret",
                ],
                "prevention": "Use short-lived tokens (15min), implement token refresh, alert on 401 rate spike",
            }
        ],
        "similar_incidents": [
            {"id": "INC-2025-0112", "title": "JWT signing key rotated without restarting consumers", "resolution": "Restarted all services to pick up new JWKS, added graceful key rotation with overlap period", "mttr_min": 9, "outcome": "RESOLVED"},
        ],
    },
}

_UNKNOWN_KNOWLEDGE = {
    "rfcs": [
        {"id": "SRE Book: Chapter 14", "title": "Managing Incidents", "relevance": "Incident command structure, escalation, communication"},
    ],
    "runbooks": [
        {
            "title": "Unknown Incident — General Investigation Runbook",
            "steps": [
                "1. Establish incident commander and communication channel",
                "2. Collect: logs, metrics, traces for all affected services",
                "3. Check recent deployments: git log --since='2 hours ago'",
                "4. Check infrastructure changes: Terraform/CloudFormation recent applies",
                "5. Escalate to domain expert with full evidence package",
            ],
            "prevention": "Improve observability coverage, add structured logging to all services",
        }
    ],
    "similar_incidents": [],
}


class KnowledgeAgent:
    name = "KnowledgeAgent"

    def run(self, reasoning: dict) -> dict:
        """
        Look up RFCs, runbooks, and similar past incidents for the classified
        incident type. Returns a knowledge context dict attached to the incident.
        """
        incident_type = reasoning.get("incident_type")
        is_unknown = reasoning.get("_unknown", False)

        if is_unknown or not incident_type or incident_type not in _KNOWLEDGE:
            kb = _UNKNOWN_KNOWLEDGE
            print(f"[{self.name}] ⚠  Unknown incident type — returning general investigation runbook")
        else:
            kb = _KNOWLEDGE[incident_type]
            print(f"[{self.name}] 📚 Found {len(kb['rfcs'])} RFCs, {len(kb['runbooks'])} runbooks, "
                  f"{len(kb['similar_incidents'])} similar incidents for [{incident_type}]")

        # Synthesize a recommended approach from similar incident outcomes
        recommendation = self._synthesize(reasoning, kb)

        return {
            "incident_type": incident_type,
            "relevant_rfcs": kb["rfcs"],
            "runbooks": kb["runbooks"],
            "similar_incidents": kb["similar_incidents"],
            "recommended_approach": recommendation,
        }

    def _synthesize(self, reasoning: dict, kb: dict) -> str:
        """
        Build a concise recommended approach from past incident outcomes.
        In production this would call Gemini with the full KB context.
        """
        similar = kb.get("similar_incidents", [])
        runbook = kb["runbooks"][0] if kb.get("runbooks") else None

        if not similar and not runbook:
            return "No historical data available. Follow general investigation runbook."

        resolved = [s for s in similar if s.get("outcome") == "RESOLVED"]
        avg_mttr = round(sum(s["mttr_min"] for s in resolved) / len(resolved), 1) if resolved else None

        parts = []
        if resolved:
            parts.append(f"Based on {len(resolved)} similar past incident(s) (avg MTTR: {avg_mttr} min):")
            parts.append(f"  Most recent resolution: {resolved[-1]['resolution']}")
        if runbook:
            parts.append(f"Recommended runbook: '{runbook['title']}'")
            parts.append(f"  Prevention: {runbook['prevention']}")

        return "\n".join(parts)
