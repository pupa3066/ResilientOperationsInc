"""
Incident Report Generator

Produces a structured incident report from a resolved incident dict.
Uses Gemini if available, falls back to template-based generation.
"""
import os, json
from datetime import datetime, timezone


def generate_report(incident: dict) -> dict:
    if os.getenv("MOCK_GEMINI") != "1":
        try:
            return _gemini_report(incident)
        except Exception:
            pass
    return _template_report(incident)


def _template_report(incident: dict) -> dict:
    r = incident["reasoning"]
    summary = incident.get("summary", {})
    steps = incident["steps"]
    decisions = incident["decisions"]

    actions_taken = [
        s["action"] for s in steps
        if decisions.get(str(s["step"])) in ("approve", "auto")
    ]
    actions_rejected = [
        s["action"] for s in steps
        if decisions.get(str(s["step"])) == "reject"
    ]
    actions_blocked = [
        s["action"] for s in steps
        if decisions.get(str(s["step"])) == "blocked"
    ]

    created = incident.get("created_at", "")
    updated = incident.get("updated_at", "")

    # Rough MTTR in minutes
    try:
        t0 = datetime.fromisoformat(created)
        t1 = datetime.fromisoformat(updated)
        mttr_min = round((t1 - t0).total_seconds() / 60, 1)
    except Exception:
        mttr_min = None

    return {
        "incident_id": f"INC-{incident['id'].upper()}",
        "title": r.get("incident_title", "Unknown Incident"),
        "severity": _severity(r.get("confidence_pct", 0)),
        "status": incident["status"],
        "source": incident["source"],
        "root_cause": r.get("root_cause"),
        "confidence_pct": r.get("confidence_pct"),
        "blast_radius": r.get("blast_radius", []),
        "timeline": {
            "detected_at": created,
            "resolved_at": updated,
            "mttr_minutes": mttr_min,
        },
        "actions_taken": actions_taken,
        "actions_rejected": actions_rejected,
        "actions_blocked": actions_blocked,
        "summary": summary,
        "elastic_signals": incident.get("elastic_context", {}).get("signals_used", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _severity(confidence: int) -> str:
    if confidence >= 90:
        return "P0"
    if confidence >= 70:
        return "P1"
    return "P2"


def _gemini_report(incident: dict) -> dict:
    from google import genai

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    prompt = f"""Generate a concise incident report as JSON for this resolved incident:

{json.dumps({
    "title": incident["reasoning"].get("incident_title"),
    "root_cause": incident["reasoning"].get("root_cause"),
    "blast_radius": incident["reasoning"].get("blast_radius"),
    "actions_taken": [s["action"] for s in incident["steps"] if incident["decisions"].get(str(s["step"])) in ("approve", "auto")],
    "status": incident["status"],
}, indent=2)}

Return JSON with keys: incident_id, title, severity (P0/P1/P2), executive_summary, root_cause, actions_taken, lessons_learned, recommendations.
"""
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    result = json.loads(response.text)
    result["incident_id"] = f"INC-{incident['id'].upper()}"
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    return result
