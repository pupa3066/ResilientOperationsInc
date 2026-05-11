# Incident Simulator

Runs 3 local services on your laptop to generate **real** logs and incidents.

## Start Services (3 terminals)

```bash
# Terminal 1 — DB service
cd incident_simulator && python3 db_service.py

# Terminal 2 — Payment service  
cd incident_simulator && python3 payment_service.py

# Terminal 3 — API Gateway
cd incident_simulator && python3 api_gateway.py
```

## Generate Traffic

```bash
# Terminal 4
cd incident_simulator && python3 traffic_gen.py
```

## Trigger an Incident

**Kill the DB** (Ctrl+C on Terminal 1) → payment-svc logs connection errors → api-gateway logs 503s → real cascade incident in `logs/`

## Read the Logs

```bash
tail -f incident_simulator/logs/api-gateway.log
tail -f incident_simulator/logs/payment-service.log
```

## Incidents You Can Create

| Action | Incident Type |
|---|---|
| Kill db_service | DB connection pool exhaustion |
| Add `time.sleep(5)` to db_service | Latency spike cascade |
| Set `FAIL_MODE = True` in db_service | 100% error rate |
| Kill payment_service | Upstream service unavailable |
