"""
FastAPI Backend — Incident Lifecycle Orchestrator

Exposes the multi-agent pipeline as a REST API.

Lifecycle:
  DETECTED → ANALYZING → PLANNING → PENDING_APPROVAL → EXECUTING → RESOLVED

Endpoints:
  POST /incidents/run              — detect + analyze all current log signals
  GET  /incidents/{id}             — get incident state
  POST /incidents/{id}/approve     — approve/reject a pending MUTATING step
  GET  /incidents/{id}/report      — get the auto-generated incident report
"""
import os, uuid, asyncio, json
from pathlib import Path
from datetime import datetime, timezone
from typing import Literal
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.detection_agent import DetectionAgent
from agents.reasoning_agent import ReasoningAgent
from agents.knowledge_agent import KnowledgeAgent
from planner.plan import mock_plan, plan as gemini_plan
from reports.generator import generate_report
from observation.elastic_mcp import ElasticMCP

app = FastAPI(title="ResilienceOps API", version="0.5.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_DASHBOARD = Path(__file__).parent / "dashboard.html"


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _DASHBOARD.read_text()

# In-memory store (replace with DB for production)
_incidents: dict[str, dict] = {}

# WebSocket subscribers: inc_id -> list of active connections
_subscribers: dict[str, list[WebSocket]] = {}

IncidentStatus = Literal[
    "DETECTED", "ANALYZING", "PLANNING",
    "PENDING_APPROVAL", "EXECUTING", "RESOLVED", "PARTIALLY_RESOLVED"
]


async def _emit(inc_id: str, event: str, data: dict):
    """Broadcast a JSON event to all WebSocket subscribers for an incident."""
    msg = json.dumps({"event": event, "data": data})
    for ws in list(_subscribers.get(inc_id, [])):
        try:
            await ws.send_text(msg)
        except Exception:
            _subscribers[inc_id].remove(ws)


# ── Models ────────────────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    step: int
    decision: Literal["approve", "reject"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_incident(signal: dict, reasoning: dict, plan: dict, knowledge: dict) -> dict:
    inc_id = str(uuid.uuid4())[:8]
    steps = plan["plan"]
    return {
        "id": inc_id,
        "source": signal["source"],
        "status": "PENDING_APPROVAL",
        "created_at": _now(),
        "updated_at": _now(),
        "signal": signal,
        "reasoning": reasoning,
        "knowledge": knowledge,
        "steps": steps,
        "decisions": {},
        "elastic_context": ElasticMCP().query(signal),
    }


def _apply_decisions(incident: dict) -> dict:
    """Execute all approved/auto steps, block dependents of rejected steps."""
    steps = incident["steps"]
    decisions = incident["decisions"]
    rejected: set[int] = {int(k) for k, v in decisions.items() if v in ("reject", "blocked")}

    approved = rejected_count = blocked = 0

    for step in steps:
        n = step["step"]
        if str(n) in decisions:
            d = decisions[str(n)]
            if d == "auto":
                approved += 1
            elif d == "approve":
                approved += 1
            elif d == "reject":
                rejected_count += 1
            elif d == "blocked":
                blocked += 1
            continue

        # Auto-execute READ_ONLY
        if step["type"] == "READ_ONLY":
            decisions[str(n)] = "auto"
            approved += 1
            continue

        # Check dependency blocks
        blocker = next((dep for dep in step.get("depends_on", []) if dep in rejected), None)
        if blocker:
            decisions[str(n)] = "blocked"
            rejected.add(n)
            blocked += 1
            continue

        # Still awaiting human decision
        incident["status"] = "PENDING_APPROVAL"
        return incident

    # All steps resolved
    incident["status"] = "RESOLVED" if rejected_count == 0 and blocked == 0 else "PARTIALLY_RESOLVED"
    incident["summary"] = {"approved": approved, "rejected": rejected_count, "blocked": blocked}
    incident["updated_at"] = _now()
    return incident


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/incidents/run", status_code=201)
async def run_pipeline():
    """Detect signals, reason, plan — returns list of created incident IDs."""
    detection = DetectionAgent()
    reasoning_agent = ReasoningAgent()
    knowledge_agent = KnowledgeAgent()

    signals = detection.run()
    if not signals:
        return {"incidents": [], "message": "No incidents detected"}

    created = []
    for signal in signals:
        reasoning = reasoning_agent.run(signal)
        knowledge = knowledge_agent.run(reasoning)
        if os.getenv("MOCK_GEMINI") == "1":
            plan = mock_plan(reasoning)
        else:
            try:
                plan = gemini_plan(reasoning)
            except Exception:
                plan = mock_plan(reasoning)
        incident = _build_incident(signal, reasoning, plan, knowledge)
        incident = _apply_decisions(incident)
        _incidents[incident["id"]] = incident

        # Notify any subscribers already connected (e.g. dashboard polling /incidents first)
        for s in incident["steps"]:
            if incident["decisions"].get(str(s["step"])) == "auto":
                await _emit(incident["id"], "step_executed", {"step": s["step"], "action": s["action"]})

        if incident["status"] == "PENDING_APPROVAL":
            for s in incident["steps"]:
                if incident["decisions"].get(str(s["step"]), "pending") == "pending" and s["type"] == "MUTATING":
                    await _emit(incident["id"], "approval_required", {"step": s["step"], "action": s["action"], "risk": s["risk"]})
                    break

        created.append({
            "id": incident["id"],
            "source": incident["source"],
            "status": incident["status"],
            "title": reasoning.get("incident_title"),
            "confidence_pct": reasoning.get("confidence_pct"),
        })

    return {"incidents": created}


@app.get("/incidents/{inc_id}")
def get_incident(inc_id: str):
    inc = _incidents.get(inc_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    return {
        "id": inc["id"],
        "source": inc["source"],
        "status": inc["status"],
        "created_at": inc["created_at"],
        "updated_at": inc["updated_at"],
        "title": inc["reasoning"].get("incident_title"),
        "root_cause": inc["reasoning"].get("root_cause"),
        "confidence_pct": inc["reasoning"].get("confidence_pct"),
        "blast_radius": inc["reasoning"].get("blast_radius"),
        "knowledge": inc.get("knowledge"),
        "steps": [
            {**s, "decision": inc["decisions"].get(str(s["step"]), "pending")}
            for s in inc["steps"]
        ],
        "elastic_context": inc.get("elastic_context"),
        "summary": inc.get("summary"),
    }


@app.post("/incidents/{inc_id}/approve")
async def approve_step(inc_id: str, body: ApprovalRequest):
    inc = _incidents.get(inc_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    if inc["status"] not in ("PENDING_APPROVAL",):
        raise HTTPException(400, f"Incident is {inc['status']}, not awaiting approval")

    step_map = {s["step"]: s for s in inc["steps"]}
    if body.step not in step_map:
        raise HTTPException(400, f"Step {body.step} not found")

    step = step_map[body.step]
    if step["type"] == "READ_ONLY":
        raise HTTPException(400, "READ_ONLY steps are auto-executed, no approval needed")
    if str(body.step) in inc["decisions"]:
        raise HTTPException(400, f"Step {body.step} already decided: {inc['decisions'][str(body.step)]}")

    inc["decisions"][str(body.step)] = body.decision
    inc["updated_at"] = _now()

    event = "step_approved" if body.decision == "approve" else "step_rejected"
    await _emit(inc_id, event, {"step": body.step, "action": step["action"], "risk": step["risk"]})

    prev_status = inc["status"]
    inc = _apply_decisions(inc)
    _incidents[inc_id] = inc

    # Notify about any newly blocked steps
    for s in inc["steps"]:
        if inc["decisions"].get(str(s["step"])) == "blocked":
            await _emit(inc_id, "step_blocked", {"step": s["step"], "action": s["action"]})

    # Notify about next step needing approval
    if inc["status"] == "PENDING_APPROVAL":
        for s in inc["steps"]:
            if inc["decisions"].get(str(s["step"]), "pending") == "pending" and s["type"] == "MUTATING":
                await _emit(inc_id, "approval_required", {"step": s["step"], "action": s["action"], "risk": s["risk"]})
                break

    if inc["status"] != prev_status:
        await _emit(inc_id, "status_changed", {"status": inc["status"]})

    if inc["status"] in ("RESOLVED", "PARTIALLY_RESOLVED"):
        await _emit(inc_id, "resolved", {"status": inc["status"], "summary": inc.get("summary")})

    return {
        "id": inc_id,
        "step": body.step,
        "decision": body.decision,
        "status": inc["status"],
        "summary": inc.get("summary"),
    }


@app.get("/incidents/{inc_id}/report")
def get_report(inc_id: str):
    inc = _incidents.get(inc_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    if inc["status"] not in ("RESOLVED", "PARTIALLY_RESOLVED"):
        raise HTTPException(400, f"Report not available until resolved (current: {inc['status']})")
    return generate_report(inc)


@app.get("/incidents")
def list_incidents():
    return [
        {"id": v["id"], "source": v["source"], "status": v["status"],
         "title": v["reasoning"].get("incident_title"), "created_at": v["created_at"]}
        for v in _incidents.values()
    ]


@app.websocket("/incidents/{inc_id}/ws")
async def incident_ws(inc_id: str, websocket: WebSocket):
    """
    Stream real-time incident events to the client.

    Events emitted:
      connected          — on join, sends current incident snapshot
      step_executed      — a READ_ONLY step was auto-executed
      step_approved      — a MUTATING step was approved by SRE
      step_rejected      — a MUTATING step was rejected
      step_blocked       — a step was blocked due to rejected dependency
      approval_required  — a MUTATING step is waiting for SRE decision
      status_changed     — incident status transitioned
      resolved           — incident fully resolved, includes summary
    """
    if inc_id not in _incidents:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    _subscribers.setdefault(inc_id, []).append(websocket)

    # Send current state immediately on connect
    inc = _incidents[inc_id]
    await websocket.send_text(json.dumps({
        "event": "connected",
        "data": {
            "id": inc_id,
            "status": inc["status"],
            "title": inc["reasoning"].get("incident_title"),
            "steps": [
                {**s, "decision": inc["decisions"].get(str(s["step"]), "pending")}
                for s in inc["steps"]
            ],
        }
    }))

    try:
        while True:
            await asyncio.sleep(30)  # keep-alive; events are pushed via _emit
    except WebSocketDisconnect:
        _subscribers[inc_id].remove(websocket)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "elastic_mcp": ElasticMCP().health(),
        "gemini": "live" if os.getenv("MOCK_GEMINI") != "1" and os.getenv("GEMINI_API_KEY") else "mock",
        "incidents_count": len(_incidents),
    }
