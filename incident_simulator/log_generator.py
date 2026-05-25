"""
Generates real-looking SRE incident logs for 12 incident types.
Run: python3 incident_simulator/log_generator.py
"""
import time, random, os
from datetime import datetime, timezone

SCENARIOS = {
    "1": ("DB connection pool exhaustion", [
        ("ERROR", "payment-svc",  "HikariPool-1 - Connection is not available, request timed out after 30000ms"),
        ("ERROR", "payment-svc",  "Unable to acquire JDBC Connection — pool size: 50, active: 50, idle: 0"),
        ("ERROR", "order-svc",    "Downstream payment-svc timeout after 30s — checkout failed"),
        ("WARN",  "order-svc",    "Retry attempt 3/3 failed — circuit breaker OPEN"),
        ("WARN",  "postgres",     "max_connections=100 reached — new connections rejected"),
        ("WARN",  "postgres",     "Long-running query detected: SELECT * FROM orders (runtime: 47s)"),
        ("ERROR", "api-gateway",  "POST /checkout 503 Service Unavailable"),
    ]),
    "2": ("Network packet loss / AZ degradation", [
        ("WARN",  "vpc-flow",     "18% packet loss detected on subnet-az-b (10.0.1.0/24)"),
        ("ERROR", "api-gateway",  "Upstream connect error or disconnect/reset before headers"),
        ("ERROR", "rds-proxy",    "Connection pool exhausted: max_connections=100 active=100 idle=0"),
        ("ERROR", "lambda",       "Task timed out after 15.00 seconds"),
        ("ERROR", "lambda",       "ECONNREFUSED 10.0.1.45:5432 — database unreachable"),
        ("ERROR", "health-check", "Target group tg-api-az-b: 0/3 healthy instances"),
    ]),
    "3": ("OOM kill / CrashLoopBackOff", [
        ("ERROR",    "auth-svc",   "java.lang.OutOfMemoryError: Java heap space"),
        ("ERROR",    "auth-svc",   "Process killed: OOMKiller — memory limit 512Mi exceeded"),
        ("ERROR",    "api-gateway","GET /login 502 Bad Gateway — upstream auth-svc unreachable"),
        ("ERROR",    "api-gateway","GET /profile 502 Bad Gateway"),
        ("WARN",     "k8s",        "Pod auth-svc-7d9f restarted 4 times in last 5 minutes (CrashLoopBackOff)"),
        ("CRITICAL", "monitoring", "auth-svc error rate 94% — SLO breach imminent"),
    ]),
    "4": ("Disk full / ENOSPC", [
        ("ERROR",    "postgres",   "could not write to file 'pg_wal/000000010000001': No space left on device"),
        ("ERROR",    "api-gateway","Failed to write access log: ENOSPC — disk full"),
        ("ERROR",    "log-agent",  "disk usage 100% on /var/log — dropping log entries"),
        ("WARN",     "monitoring", "inode usage 98% on /dev/xvda1"),
        ("CRITICAL", "postgres",   "WAL archiving failed — disk full, database at risk"),
        ("ERROR",    "order-svc",  "Failed to write temp file during order processing: No space left on device"),
    ]),
    "5": ("CPU throttling / high load", [
        ("WARN",  "report-svc",   "CPU throttling detected — cpu.cfs_throttled_periods_total increasing"),
        ("WARN",  "report-svc",   "Request queue depth: 847 — processing degraded"),
        ("ERROR", "api-gateway",  "GET /reports 504 Gateway Timeout — upstream report-svc unresponsive"),
        ("WARN",  "k8s",          "Pod report-svc-5f9d CPU usage 100% of limit (500m)"),
        ("ERROR", "report-svc",   "Thread pool exhausted: all 50 worker threads busy"),
        ("WARN",  "monitoring",   "load average 15min: 24.3 (8 cores) — system overloaded"),
    ]),
    "6": ("TLS certificate expiry", [
        ("ERROR", "ingress",      "SSL handshake failed: certificate expired (notAfter=2026-05-24T00:00:00Z)"),
        ("ERROR", "api-gateway",  "x509: certificate has expired or is not yet valid"),
        ("ERROR", "payment-svc",  "CERTIFICATE_VERIFY_FAILED connecting to stripe.com:443"),
        ("ERROR", "ingress",      "TLS handshake error from 10.0.0.1:52341: tls: no certificates configured"),
        ("WARN",  "cert-manager", "Certificate api-tls-cert expires in 0 days — renewal failed"),
        ("ERROR", "monitoring",   "HTTPS health check failed: SSL certificate problem: certificate has expired"),
    ]),
    "7": ("Failed deployment / rollout stuck", [
        ("WARN",  "k8s",          "Deployment api-svc rollout stuck: 0/3 new pods ready after 5 minutes"),
        ("ERROR", "k8s",          "Pod api-svc-new-7f8d: Back-off restarting failed container (CrashLoopBackOff)"),
        ("ERROR", "api-svc",      "Failed to start: missing required environment variable DATABASE_URL"),
        ("WARN",  "k8s",          "Readiness probe failed: HTTP probe failed with statuscode: 500"),
        ("ERROR", "k8s",          "ImagePullBackOff: failed to pull image api-svc:v2.1.0 — manifest unknown"),
        ("WARN",  "monitoring",   "Deployment api-svc: 0 available replicas — all traffic to old pods"),
    ]),
    "8": ("DNS resolution failure", [
        ("ERROR", "order-svc",    "getaddrinfo ENOTFOUND payment-svc.default.svc.cluster.local"),
        ("ERROR", "auth-svc",     "DNS resolution failed: NXDOMAIN for user-db.internal"),
        ("ERROR", "api-gateway",  "upstream host not found: lookup inventory-svc: no such host"),
        ("WARN",  "k8s",          "CoreDNS pod coredns-5d78c9869d-xk2p2 restarted — OOMKilled"),
        ("ERROR", "payment-svc",  "dial tcp: lookup stripe.com on 10.96.0.10:53: read udp: i/o timeout"),
        ("CRITICAL","monitoring", "Service discovery broken — DNS resolution failing cluster-wide"),
    ]),
    "9": ("Rate limit / quota exhaustion", [
        ("WARN",  "payment-svc",  "Stripe API returned 429 Too Many Requests — rate limit exceeded"),
        ("ERROR", "payment-svc",  "RateLimitExceeded: quota 1000 req/min exhausted, retry after 60s"),
        ("WARN",  "order-svc",    "Retry attempt 5/5 failed — upstream still returning 429"),
        ("ERROR", "api-gateway",  "POST /payment 503 — downstream payment-svc rate limited"),
        ("WARN",  "monitoring",   "payment-svc outbound request rate: 1847/min (limit: 1000/min)"),
        ("ERROR", "payment-svc",  "quota exceeded for API key sk_live_xxx — contact support"),
    ]),
    "10": ("Cascading timeout / circuit breaker storm", [
        ("WARN",  "inventory-svc","Response time p99: 8400ms (SLO: 500ms) — upstream timeout"),
        ("ERROR", "order-svc",    "Downstream inventory-svc timeout after 30s — circuit breaker OPEN"),
        ("ERROR", "payment-svc",  "Downstream order-svc timeout after 30s — circuit breaker OPEN"),
        ("ERROR", "api-gateway",  "POST /checkout 504 Gateway Timeout — retry exhausted"),
        ("WARN",  "order-svc",    "Thread pool exhausted: all 100 threads waiting on inventory-svc"),
        ("CRITICAL","monitoring", "Circuit breaker storm: 4 services OPEN — checkout flow completely down"),
    ]),
    "11": ("Data corruption / deserialization error", [
        ("ERROR", "consumer-svc", "Failed to deserialize message from topic orders: checksum mismatch"),
        ("ERROR", "consumer-svc", "Avro schema mismatch: expected schema v3, got v4 — parse error"),
        ("ERROR", "consumer-svc", "invalid data in field 'amount': expected float, got string"),
        ("WARN",  "kafka",        "Consumer group order-processor lag: 84,291 messages — processing stalled"),
        ("ERROR", "consumer-svc", "malformed JSON in message offset 8291847: unexpected token at position 142"),
        ("WARN",  "monitoring",   "DLQ topic orders-dlq message count: 12,847 — data pipeline degraded"),
    ]),
    "12": ("Auth / token failure", [
        ("ERROR", "api-gateway",  "401 Unauthorized: JWT token expired (exp: 2026-05-25T10:00:00Z)"),
        ("ERROR", "user-svc",     "403 Forbidden: service account api-svc lacks permission 'users:read'"),
        ("ERROR", "payment-svc",  "auth failed: invalid token signature — possible key rotation issue"),
        ("WARN",  "auth-svc",     "token expired for 847 active sessions — mass re-auth required"),
        ("ERROR", "api-gateway",  "GET /profile 401 Unauthorized — token expired"),
        ("WARN",  "monitoring",   "401 error rate: 94% of requests — auth service or token issue"),
    ]),
}

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def run():
    print("\nChoose incident to simulate:")
    for k, (name, _) in SCENARIOS.items():
        print(f"  {k:>2}. {name}")
    choice = input("\nEnter 1-12 (or 'all' to generate all): ").strip() or "1"

    os.makedirs("logs", exist_ok=True)

    targets = list(SCENARIOS.items()) if choice == "all" else [(choice, SCENARIOS.get(choice, SCENARIOS["1"]))]

    for key, (name, events) in targets:
        log_file = f"logs/incident-{key}.log"
        print(f"\n[+] Simulating: {name}")
        print(f"[+] Writing to: {log_file}")

        with open(log_file, "w") as f:
            for _ in range(3):  # 3 waves
                for level, service, msg in events:
                    line = f'{now()} level={level} service={service} msg="{msg}"'
                    if choice != "all":
                        print(line)
                    f.write(line + "\n")
                    time.sleep(random.uniform(0.05, 0.2) if choice == "all" else random.uniform(0.1, 0.4))
                time.sleep(0.5)

        print(f"[+] Done → {log_file} ({len(events) * 3} lines)")

if __name__ == "__main__":
    run()
