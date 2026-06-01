"""
Historical Incident Store

Persists resolved incidents and retrieves similar past incidents
to improve root-cause accuracy and resolution speed.

Storage: incidents_history.jsonl (append-only, one JSON object per line)
Matching: incident_type + keyword overlap scoring
"""
import json, os
from datetime import datetime, timezone
from pathlib import Path

_STORE_PATH = Path(__file__).parent / "incidents_history.jsonl"


def save(incident: dict):
    """Persist a resolved incident to the history store."""
    record = {
        "id": incident["id"],
        "source": incident["source"],
        "status": incident["status"],
        "incident_type": incident["reasoning"].get("incident_type"),
        "title": incident["reasoning"].get("incident_title"),
        "root_cause": incident["reasoning"].get("root_cause"),
        "confidence_pct": incident["reasoning"].get("confidence_pct"),
        "blast_radius": incident["reasoning"].get("blast_radius", []),
        "services": incident["signal"].get("services", []),
        "steps": incident["steps"],
        "decisions": incident["decisions"],
        "actions_taken": [
            s["action"] for s in incident["steps"]
            if incident["decisions"].get(str(s["step"])) in ("approve", "auto")
        ],
        "actions_rejected": [
            s["action"] for s in incident["steps"]
            if incident["decisions"].get(str(s["step"])) == "reject"
        ],
        "created_at": incident.get("created_at"),
        "resolved_at": incident.get("updated_at"),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(_STORE_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def load_all() -> list[dict]:
    """Load all historical incidents."""
    if not _STORE_PATH.exists():
        return []
    records = []
    for line in _STORE_PATH.read_text().splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def find_similar(reasoning: dict, top_k: int = 3) -> list[dict]:
    """
    Find similar past incidents by type match + keyword overlap.
    Returns top_k most relevant historical incidents with similarity scores.
    """
    history = load_all()
    if not history:
        return []

    incident_type = reasoning.get("incident_type")
    root_cause = reasoning.get("root_cause", "").lower()
    title = reasoning.get("incident_title", "").lower()
    query_words = set((root_cause + " " + title).split())

    scored = []
    for record in history:
        score = 0
        # Type match is strongest signal
        if record.get("incident_type") == incident_type:
            score += 5
        # Keyword overlap in root cause
        rec_words = set((record.get("root_cause", "") + " " + record.get("title", "")).lower().split())
        overlap = len(query_words & rec_words)
        score += overlap
        # Service overlap
        rec_services = set(record.get("services", []))
        blast = set(reasoning.get("blast_radius", []))
        score += len(rec_services & blast) * 2

        if score > 0:
            scored.append((score, record))

    scored.sort(key=lambda x: -x[0])
    return [
        {**r, "_similarity_score": s}
        for s, r in scored[:top_k]
    ]


def stats() -> dict:
    """Return summary stats about the history store."""
    history = load_all()
    if not history:
        return {"total": 0, "by_type": {}}
    by_type: dict[str, int] = {}
    for r in history:
        t = r.get("incident_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    return {"total": len(history), "by_type": by_type}
