"""
Real-life SRE incident seed data.
Based on: AWS us-east-1 (2024), Cloudflare BGP (2023), DB pool exhaustion (common pattern).
"""
from datetime import datetime, timezone

def ts(offset_min: int = 0) -> str:
    from datetime import timedelta
    return (datetime(2024, 3, 12, 14, 0, tzinfo=timezone.utc) +
            timedelta(minutes=offset_min)).isoformat()

INCIDENTS = [
    # ── Incident 1: AWS us-east-1 network misconfiguration (2024) ──────────
    {
        "id": "INC-2024-0312",
        "title": "AWS us-east-1 AZ-b packet loss — cascading RDS/Lambda failures",
        "logs": [
            {"time": ts(0),  "service": "api-gateway",   "level": "ERROR", "msg": "Upstream connect error or disconnect/reset before headers. retried and the latest reset reason: connection timeout"},
            {"time": ts(0),  "service": "api-gateway",   "level": "ERROR", "msg": "upstream connect error or disconnect/reset before headers"},
            {"time": ts(1),  "service": "rds-proxy",     "level": "ERROR", "msg": "Connection pool exhausted: max_connections=100 active=100 idle=0"},
            {"time": ts(1),  "service": "rds-proxy",     "level": "ERROR", "msg": "Timeout acquiring connection from pool after 30000ms"},
            {"time": ts(2),  "service": "lambda-worker", "level": "ERROR", "msg": "Task timed out after 15.00 seconds"},
            {"time": ts(2),  "service": "lambda-worker", "level": "ERROR", "msg": "ECONNREFUSED 10.0.1.45:5432 — database unreachable"},
            {"time": ts(3),  "service": "vpc-flow",      "level": "WARN",  "msg": "18% packet loss detected on subnet-az-b (10.0.1.0/24) → 10.0.2.0/24"},
            {"time": ts(4),  "service": "health-check",  "level": "ERROR", "msg": "Target group tg-api-az-b: 0/3 healthy instances"},
        ],
        "metrics": {
            "error_rate_per_min":   847,
            "latency_p99_ms":       4200,
            "latency_baseline_ms":  180,
            "rds_timeouts_per_min": 340,
            "lambda_cold_start_failure_pct": 62,
            "packet_loss_pct":      18,
            "affected_az":          "us-east-1b",
        },
        "traces": [
            {"trace_id": "abc-001", "span": "client → api-gateway",   "duration_ms": 4198, "status": "timeout"},
            {"trace_id": "abc-001", "span": "api-gateway → rds-proxy", "duration_ms": 3950, "status": "connection_refused"},
            {"trace_id": "abc-001", "span": "rds-proxy → rds-db",      "duration_ms": None, "status": "dropped"},
        ],
    },

    # ── Incident 2: Cloudflare BGP route leak (2023) ────────────────────────
    {
        "id": "INC-2023-0627",
        "title": "Cloudflare BGP misconfiguration — global traffic drop",
        "logs": [
            {"time": ts(0),  "service": "bgp-router",    "level": "ERROR", "msg": "BGP session reset: peer 198.51.100.1 — hold timer expired"},
            {"time": ts(0),  "service": "bgp-router",    "level": "ERROR", "msg": "Route withdrawal: 104.16.0.0/12 removed from routing table"},
            {"time": ts(1),  "service": "cdn-edge",      "level": "ERROR", "msg": "No route to host: origin pull failed for 104.16.132.229"},
            {"time": ts(1),  "service": "cdn-edge",      "level": "ERROR", "msg": "Cache MISS rate 100% — origin unreachable"},
            {"time": ts(2),  "service": "dns-resolver",  "level": "WARN",  "msg": "1.1.1.1 query timeout — upstream resolver not responding"},
            {"time": ts(3),  "service": "monitoring",    "level": "CRITICAL", "msg": "Global traffic drop 65% — all PoPs affected"},
        ],
        "metrics": {
            "traffic_drop_pct":     65,
            "affected_pops":        152,
            "dns_query_timeout_pct": 78,
            "origin_pull_failure_pct": 100,
            "bgp_routes_withdrawn": 1,
        },
        "traces": [
            {"trace_id": "bgp-001", "span": "user → cloudflare-edge",  "duration_ms": None,  "status": "no_route"},
            {"trace_id": "bgp-001", "span": "cloudflare-edge → origin", "duration_ms": None,  "status": "dropped"},
        ],
    },

    # ── Incident 3: DB connection pool exhaustion (common SRE pattern) ──────
    {
        "id": "INC-2024-0891",
        "title": "Payment service DB connection pool exhaustion — checkout failures",
        "logs": [
            {"time": ts(0),  "service": "payment-svc",   "level": "ERROR", "msg": "HikariPool-1 - Connection is not available, request timed out after 30000ms"},
            {"time": ts(0),  "service": "payment-svc",   "level": "ERROR", "msg": "Unable to acquire JDBC Connection — pool size: 50, active: 50, idle: 0"},
            {"time": ts(1),  "service": "order-svc",     "level": "ERROR", "msg": "Downstream payment-svc timeout after 30s — checkout failed"},
            {"time": ts(1),  "service": "order-svc",     "level": "WARN",  "msg": "Retry attempt 3/3 failed — circuit breaker OPEN"},
            {"time": ts(2),  "service": "postgres-db",   "level": "WARN",  "msg": "max_connections=100 reached — new connections rejected"},
            {"time": ts(2),  "service": "postgres-db",   "level": "WARN",  "msg": "Long-running query detected: SELECT * FROM orders (runtime: 47s, pid: 2341)"},
            {"time": ts(3),  "service": "api-gateway",   "level": "ERROR", "msg": "POST /checkout 503 Service Unavailable"},
        ],
        "metrics": {
            "checkout_failure_rate_pct": 89,
            "db_active_connections":     100,
            "db_max_connections":        100,
            "long_query_runtime_sec":    47,
            "circuit_breaker_state":     "OPEN",
            "p99_latency_ms":            31200,
        },
        "traces": [
            {"trace_id": "pay-001", "span": "user → api-gateway",      "duration_ms": 31200, "status": "503"},
            {"trace_id": "pay-001", "span": "api-gateway → order-svc", "duration_ms": 30100, "status": "timeout"},
            {"trace_id": "pay-001", "span": "order-svc → payment-svc", "duration_ms": 30050, "status": "timeout"},
            {"trace_id": "pay-001", "span": "payment-svc → postgres",  "duration_ms": None,  "status": "pool_exhausted"},
        ],
    },
]
