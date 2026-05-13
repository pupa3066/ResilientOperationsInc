"""
Observation Layer — reads incident log files and converts them into signals.

Edge cases handled:
  - Empty logs (edge case 6):
    If a log file is empty or contains no parseable lines, it is skipped
    with a warning instead of crashing or returning a zero-signal incident
    that could confuse downstream agents.

  - Malformed logs (edge case 6):
    Lines that don't match the expected format are silently skipped.
    A file with only malformed lines is treated as empty.

  - Cascading incidents / multi-service correlation (edge case 1):
    When multiple log files share overlapping services (e.g. api-gateway
    appears in both incident-1 and incident-2), load_signals() flags them
    as potentially cascading via the 'cascade_candidates' field. The
    DetectionAgent and ReasoningAgent can use this to avoid generating
    duplicate or conflicting remediation plans.

  - New signals during remediation (edge case 4):
    load_signals() is stateless and re-reads files on every call.
    The ActionAgent can call it again mid-execution to detect new incidents
    that arrived while a remediation was in progress.
"""
import re
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "incident_simulator/logs"
LINE_RE = re.compile(r'(?P<time>\S+) level=(?P<level>\S+) service=(?P<service>\S+) msg="(?P<msg>[^"]+)"')


def parse_log(path: Path) -> list[dict]:
    """
    Parse a log file into a list of structured entries.
    Malformed lines are skipped silently (edge case 6).
    Returns empty list if file is empty or unreadable.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"[log_reader] ⚠ Could not read {path.name}: {e}")
        return []

    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if m:
            entries.append(m.groupdict())
        # malformed lines are silently skipped
    return entries


def load_signals(log_dir: Path = LOG_DIR) -> list[dict]:
    """
    Load all incident-*.log files from log_dir.

    Edge case 6 — empty/malformed logs:
      Files with no parseable entries are skipped with a warning.

    Edge case 1 — cascading incident detection:
      After loading all signals, cross-reference services across incidents.
      Any two incidents sharing a service are flagged as cascade_candidates.

    Returns list of signal dicts, each with:
      id, source, logs, error_logs, services, signal_count, cascade_candidates
    """
    log_files = sorted(log_dir.glob("incident-*.log"))

    # Edge case 6: no log files at all
    if not log_files:
        print(f"[log_reader] ⚠ No incident log files found in {log_dir}")
        return []

    signals = []
    for log_file in log_files:
        entries = parse_log(log_file)

        # Edge case 6: empty or fully malformed file — skip it
        if not entries:
            print(f"[log_reader] ⚠ {log_file.name} is empty or unreadable — skipping")
            continue

        errors   = [e for e in entries if e["level"] in ("ERROR", "CRITICAL")]
        services = list(dict.fromkeys(e["service"] for e in errors))

        signals.append({
            "id":                log_file.stem.upper().replace("-", "_"),
            "source":            log_file.name,
            "logs":              entries,
            "error_logs":        errors,
            "services":          services,
            "signal_count":      len(errors),
            "cascade_candidates": [],  # filled in below
        })

    # Edge case 1 — cascading incident detection:
    # Mark pairs of incidents that share at least one affected service
    for i, s1 in enumerate(signals):
        for j, s2 in enumerate(signals):
            if i >= j:
                continue
            shared = set(s1["services"]) & set(s2["services"])
            if shared:
                s1["cascade_candidates"].append({
                    "source": s2["source"],
                    "shared_services": list(shared),
                })
                s2["cascade_candidates"].append({
                    "source": s1["source"],
                    "shared_services": list(shared),
                })

    return signals
