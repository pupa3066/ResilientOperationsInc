"""Reads live incident log files and converts them into observation signals."""
import re
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "incident_simulator/logs"
LINE_RE = re.compile(r'(?P<time>\S+) level=(?P<level>\S+) service=(?P<service>\S+) msg="(?P<msg>[^"]+)"')

def parse_log(path: Path) -> list[dict]:
    entries = []
    for line in path.read_text().splitlines():
        m = LINE_RE.match(line)
        if m:
            entries.append(m.groupdict())
    return entries

def load_signals() -> list[dict]:
    signals = []
    for log_file in sorted(LOG_DIR.glob("incident-*.log")):
        entries = parse_log(log_file)
        errors  = [e for e in entries if e["level"] in ("ERROR", "CRITICAL")]
        services = list(dict.fromkeys(e["service"] for e in errors))
        signals.append({
            "id":         log_file.stem.upper().replace("-", "_"),
            "source":     str(log_file.name),
            "logs":       entries,
            "error_logs": errors,
            "services":   services,
            "signal_count": len(errors),
        })
    return signals
