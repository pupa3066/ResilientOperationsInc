# ResilientOperationsInc

> **AI Incident Commander** — powered by Gemini & Elastic  
> Turns high-MTTR production incidents into fast-resolved events by detecting failures, diagnosing root causes, and remediating in real time.

---

## 💡 Inspiration

Modern production systems fail in complex, cascading ways. Engineers manually correlate logs, metrics, and traces under pressure — we wanted an AI that doesn't just alert engineers, but reasons and acts during incidents.

---

## ⚙️ What it does

ResilienceOps is an AI incident commander that:

- Queries logs, metrics, and traces via **Elastic MCP**
- Diagnoses root causes with **Gemini reasoning**
- Generates step-by-step remediation plans
- Recommends safe actions with **human approval gates**
- Produces structured incident reports after resolution

---

## 🏗️ System Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER / SRE                                 │
│         (approves rollbacks, config changes, scaling decisions)     │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ HTTP
┌─────────────────────────────▼───────────────────────────────────────┐
│                        FastAPI Backend                              │
│                   (incident lifecycle orchestrator)                 │
│     detecting → analyzing → planning → pending_approval → resolved  │
└──────┬──────────────────────┬──────────────────────┬───────────────┘
       │                      │                      │
┌──────▼──────────┐  ┌────────▼─────────┐  ┌────────▼──────────────┐
│  1. OBSERVATION │  │  2. REASONING    │  │  5. HITL CONTROLLER   │
│  (Elastic MCP)  │  │  (Gemini 2.0)    │  │                       │
│                 │  │                  │  │ Gates ALL real actions │
│ • Log Ingestion │  │ • Understand     │  │ • rollback suggestion  │
│ • Search Query  │──▶  incident ctx   │  │ • config change        │
│ • Anomaly       │  │ • Build          │  │ • scaling decision     │
│   Detection     │  │   hypothesis     │  │                       │
│ • Trace         │  │   tree           │  │ User MUST approve      │
│   Correlation   │  │ • Prioritize     │  │ before execution       │
└─────────────────┘  │   root causes    │  └────────┬──────────────┘
                     │ • Decide next    │           │ approved
                     │   steps          │           │
                     └────────┬─────────┘  ┌────────▼──────────────┐
                              │            │  4. TOOL EXECUTOR      │
                     ┌────────▼─────────┐  │                       │
                     │  3. PLANNER      │  │ Safe actions only:     │
                     │                  │──▶ • Elastic queries     │
                     │ Breaks incident  │  │ • Log filtering        │
                     │ into ordered     │  │ • Metrics retrieval    │
                     │ hypothesis steps │  │ • Incident summary     │
                     │                  │  │                       │
                     │ e.g. latency     │  │ NO autonomous          │
                     │ spike plan:      │  │ destructive execution  │
                     │ 1. check deploys │  └────────┬──────────────┘
                     │ 2. error logs    │           │
                     │ 3. traffic diff  │           │
                     │ 4. svc deps      │  ┌────────▼──────────────┐
                     │ 5. root node     │  │  INCIDENT REPORT      │
                     └──────────────────┘  │  (Gemini-generated)   │
                                           │  structured + auditable│
                                           └───────────────────────┘
```

---

## 🔌 Key Modules

### 1. Observation Layer — Elastic MCP

| Tool | What it does | Example |
|---|---|---|
| **Log Query** | Fetch recent errors by service/time | `fetch last 15min errors from auth-service` |
| **Trace Correlation** | Link request traces across microservices | `trace request_id across payment → inventory → db` |
| **Metrics Tool** | Detect latency, CPU, volume anomalies | `get latency p99 for us-east-1 last 30min` |
| **Search Tool** | Semantic + keyword log search | `search logs for "connection timeout" near deploy events` |

### 2. Reasoning Agent — Gemini 2.0

- Understands full incident context
- Builds a hypothesis tree with confidence scores
- Prioritizes likely root causes with evidence citations
- Decides next investigation steps

### 3. Planner

Breaks the incident into ordered, executable steps:

```
Incident: "Latency spike in us-east-1"

Hypothesis Tree:
├── [HIGH]  Network layer issue (packet loss pattern in traces)
├── [MED]   Recent deployment gone wrong
├── [MED]   Database connection pool exhaustion
└── [LOW]   Traffic surge / DDoS

Generated Plan:
  Step 1: fetch recent deployments              ← Elastic
  Step 2: analyze error logs for affected svcs  ← Elastic
  Step 3: compare traffic patterns              ← Elastic
  Step 4: isolate service dependency chain      ← Elastic trace
  Step 5: identify root node → present to SRE
```

### 4. Tool Executor

```
READ-ONLY (auto-execute)        MUTATING (require approval)
─────────────────────────       ───────────────────────────
• query logs                    • rollback deployment
• fetch metrics                 • change config
• search traces                 • scale service up/down
• generate report               • restart pod/service
```

### 5. Human-in-the-Loop Controller

Every mutating action is gated behind SRE approval:

```
ResilienceOps → "Root cause identified (91% confidence).
                 Proposed: reroute traffic from AZ-b + scale RDS replicas.
                 Approve? [YES / NO / MODIFY]"
SRE → YES
ResilienceOps → executes actions
```

---

## 🚨 Real-World POC: AWS us-east-1 Outage 2024

### The Incident

AWS Virginia experienced cascading failures across EC2, RDS, and Lambda. Root cause: **network device misconfiguration** during a routine update triggered packet loss, cascading connection timeouts across dependent services. Teams spent **45–90 minutes** manually correlating dashboards before isolating the cause.

### How ResilienceOps Would Have Handled It

```
T+0:00  Elastic MCP detects anomaly signals
        ├── error rate spike: api-gateway (us-east-1) → 847 errors/min
        ├── latency p99: 4200ms (baseline: 180ms)
        ├── RDS connection timeouts: 340/min
        └── Lambda cold start failures: +620%

T+0:02  Gemini builds hypothesis tree
        ├── [HIGH]  Network layer issue (packet loss pattern in traces)
        ├── [MED]   Recent deployment gone wrong
        ├── [MED]   Database connection pool exhaustion
        └── [LOW]   Traffic surge / DDoS

T+0:03  Planner generates investigation steps
        Step 1: query VPC flow logs for packet drop signals     ← Elastic
        Step 2: fetch last 3 deploys in us-east-1              ← Elastic
        Step 3: trace RDS connection errors to origin service  ← Elastic
        Step 4: compare traffic volume (normal vs now)         ← Elastic
        Step 5: correlate Lambda failures with RDS timeouts    ← Elastic

T+0:06  Gemini reasoning output
        Root Cause (confidence 91%):
        "Network device misconfiguration in us-east-1 AZ-b
         causing 18% packet loss. RDS and Lambda failures are
         downstream effects, not independent root causes."

T+0:07  Planner proposes remediation
        ├── [NEEDS APPROVAL] Reroute traffic away from AZ-b
        ├── [NEEDS APPROVAL] Scale RDS read replicas in AZ-a/c
        └── [NEEDS APPROVAL] Pin Lambda to healthy AZs

T+0:08  HITL Gate — SRE receives approval request
        "ResilienceOps identified network packet loss in AZ-b
         with 91% confidence. Proposed: reroute + scale replicas.
         Estimated recovery: 4–6 min. Approve? [YES / NO / MODIFY]"

T+0:09  SRE approves → Tool Executor runs actions

T+0:13  System stabilizes
        ├── error rate: 847 → 12/min
        ├── latency p99: 4200ms → 210ms
        └── RDS connections: restored

T+0:15  Gemini generates incident report (auto)
```

### Auto-Generated Incident Report

```
INCIDENT REPORT — INC-2024-0312
─────────────────────────────────────────────────────
Severity:     P0
Duration:     13 minutes (vs industry avg 45–90 min)
Region:       us-east-1 (AZ-b)
Root Cause:   Network device misconfiguration → packet loss
Blast Radius: EC2, RDS, Lambda, API Gateway

Timeline:
  T+0:00  Anomaly detected via Elastic MCP
  T+0:06  Root cause identified (Gemini, 91% confidence)
  T+0:08  Remediation proposed + sent for approval
  T+0:09  SRE approved
  T+0:13  System restored

Actions Taken:
  ✓ Traffic rerouted from AZ-b
  ✓ RDS replicas scaled in AZ-a/c
  ✓ Lambda pinned to healthy AZs

MTTR:         13 min  (vs ~75 min manual)
Time saved:   ~62 minutes
─────────────────────────────────────────────────────
```

---

## 📐 Incident Lifecycle

```
DETECTED → ANALYZING → PLANNING → PENDING_APPROVAL → EXECUTING → RESOLVED
                                        │
                                   SRE reviews
                                   proposed action
                                   (approve / reject / modify)
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Reasoning | Google Gemini 2.0 |
| Observability | Elastic MCP Server |
| Backend | Python / FastAPI |
| Agent Orchestration | Custom multi-step pipeline |
| Human Approval | HITL gate via API |

---

## 🛡️ Production Hardening — Edge Cases

ResilienceOps handles the failure modes that break naive incident response systems:

| Edge Case | Problem | Solution |
|---|---|---|
| **False positive** | Single transient error triggers full pipeline | `MIN_SIGNALS=5` threshold + 60s cooldown in DetectionAgent |
| **Unknown incident type** | Unrecognized pattern falls through to wrong handler | Evidence-based keyword scoring; returns UNKNOWN + safe plan if confidence < 2 |
| **HITL rejection cascade** | Rejecting step 3 doesn't block dependent steps 4, 5 | `depends_on` graph in every plan step; ActionAgent blocks downstream automatically |
| **Cascading incidents** | Two root causes on shared services generate conflicting plans | Cross-reference services across incidents; warn operator of cascade candidates |
| **Incident during remediation** | New failures arrive while fix is running, get ignored | Post-remediation re-check loop; cooldown prevents re-firing same source |
| **Empty/malformed logs** | Missing or corrupt log files crash the pipeline | Graceful skip with warnings; regex non-matches silently ignored |

---

## 🚀 Quick Start

```bash
git clone https://github.com/pupa3066/ResilientOperationsInc.git
cd ResilientOperationsInc
python3 -m venv .venv && source .venv/bin/activate
pip install rich google-genai

# Generate incident logs
cd incident_simulator
echo "1" | python3 log_generator.py
echo "2" | python3 log_generator.py
echo "3" | python3 log_generator.py
cd ..

# Run full multi-agent pipeline (mock mode)
MOCK_GEMINI=1 GEMINI_API_KEY=x AUTO_APPROVE=1 python agent_main.py

# Run with real Gemini API
GEMINI_API_KEY=your_key AUTO_APPROVE=1 python agent_main.py
```

---

- Multi-agent architecture (separate detection, reasoning, execution roles)
- Historical incident learning for improved root-cause accuracy
- Real-time dashboard for live incident visualization
- Expanded integrations: Kubernetes, cloud providers, CI/CD systems
- Replay mode to simulate past outages for training and evaluation

---

## 🤖 Multi-Agent Architecture

```
DetectionAgent → ReasoningAgent → ActionAgent
```

| Agent | Owns | Output |
|---|---|---|
| **DetectionAgent** | Log ingestion, anomaly threshold, cooldown | Fired incident signals |
| **ReasoningAgent** | Gemini root cause, hypothesis tree, blast radius | Reasoning result with confidence % |
| **ActionAgent** | Plan execution, HITL gate, dependency graph, audit log | Resolution summary |

---

## 📁 Project Structure

```
ResilientOperationsInc/
├── agent_main.py              ← multi-agent entry point
├── main.py                    ← monolithic entry point (Day 1)
├── agents/
│   ├── detection_agent.py     ← threshold + cooldown + cascade detection
│   ├── reasoning_agent.py     ← Gemini root cause analysis
│   └── action_agent.py        ← plan execution + HITL + dependency graph
├── observation/
│   ├── log_reader.py          ← log ingestion + cascade cross-reference
│   ├── observe.py             ← anomaly detection display
│   └── seed_data.py           ← built-in SRE incident data
├── reasoning/
│   └── reason.py              ← evidence-based classifier + Gemini prompt
├── planner/
│   └── plan.py                ← remediation plan with depends_on graph
├── hitl/
│   ├── controller.py          ← HITL approval gate
│   └── audit_log.jsonl        ← immutable decision audit trail
├── incident_simulator/
│   ├── log_generator.py       ← generates realistic incident logs
│   └── logs/                  ← incident-1/2/3.log
└── everyday_work_log/         ← daily build logs with reasoning
```

---

## 🏆 Accomplishments

- Full end-to-end AI incident response workflow — not just a chatbot
- Real observability-driven reasoning via Elastic MCP
- Structured multi-step planning that mirrors actual SRE workflows
- Human-in-the-loop safeguards for safe, auditable operations

---

## 📚 What We Learned

- Agents need structured planning, not just prompting
- Observability data is powerful when combined with reasoning models
- Multi-step tool use is significantly harder than single-query LLM apps
- Trust and auditability are non-negotiable for production-grade agents

---

*Built for real-world SRE workflows. Inspired by the incidents that keep engineers up at night.*
