"""
Generates real-looking SRE incident logs locally. No services, no network calls.
Run: python3 incident_simulator/log_generator.py
"""
import time, random
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
    "2": ("Latency spike / network packet loss", [
        ("ERROR", "api-gateway",  "Upstream connect error or disconnect/reset before headers"),
        ("WARN",  "vpc-flow",     "18% packet loss detected on subnet-az-b (10.0.1.0/24)"),
        ("ERROR", "rds-proxy",    "Connection pool exhausted: max_connections=100 active=100 idle=0"),
        ("ERROR", "lambda",       "Task timed out after 15.00 seconds"),
        ("ERROR", "lambda",       "ECONNREFUSED 10.0.1.45:5432 — database unreachable"),
        ("ERROR", "health-check", "Target group tg-api-az-b: 0/3 healthy instances"),
    ]),
    "3": ("Service crash / OOM kill", [
        ("ERROR", "auth-svc",     "java.lang.OutOfMemoryError: Java heap space"),
        ("ERROR", "auth-svc",     "Process killed: OOMKiller — memory limit 512Mi exceeded"),
        ("ERROR", "api-gateway",  "GET /login 502 Bad Gateway — upstream auth-svc unreachable"),
        ("ERROR", "api-gateway",  "GET /profile 502 Bad Gateway"),
        ("WARN",  "k8s",          "Pod auth-svc-7d9f restarted 4 times in last 5 minutes (CrashLoopBackOff)"),
        ("CRITICAL","monitoring", "auth-svc error rate 94% — SLO breach imminent"),
    ]),
}

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def run():
    print("\nChoose incident to simulate:")
    for k, (name, _) in SCENARIOS.items():
        print(f"  {k}. {name}")
    choice = input("\nEnter 1/2/3: ").strip() or "1"
    name, events = SCENARIOS.get(choice, SCENARIOS["1"])

    log_file = f"logs/incident-{choice}.log"
    import os; os.makedirs("logs", exist_ok=True)

    print(f"\n[+] Simulating: {name}")
    print(f"[+] Writing to: {log_file}\n")

    with open(log_file, "a") as f:
        for _ in range(3):  # 3 waves of errors
            for level, service, msg in events:
                line = f'{now()} level={level} service={service} msg="{msg}"'
                print(line)
                f.write(line + "\n")
                time.sleep(random.uniform(0.1, 0.4))
            time.sleep(1)

    print(f"\n[+] Done. Logs saved to {log_file}")

if __name__ == "__main__":
    run()
