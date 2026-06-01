"""
Real-Time Log Watcher

Continuously monitors the incident log directory for new/modified files.
Triggers the detection pipeline when changes are detected.

Usage:
  python -m watcher              # run standalone
  From API: background task via /watcher/start endpoint
"""
import os, time, asyncio
from pathlib import Path
from datetime import datetime, timezone
from observation.log_reader import LOG_DIR, parse_log

# Track file state: path -> (mtime, size)
_file_state: dict[str, tuple[float, int]] = {}
_callbacks: list = []
_running = False


def scan_changes(log_dir: Path = LOG_DIR) -> list[dict]:
    """
    Scan for new or modified log files since last check.
    Returns list of change events.
    """
    global _file_state
    changes = []

    for log_file in sorted(log_dir.glob("incident-*.log")):
        key = str(log_file)
        stat = log_file.stat()
        current = (stat.st_mtime, stat.st_size)
        prev = _file_state.get(key)

        if prev is None:
            # New file
            changes.append({
                "type": "new",
                "file": log_file.name,
                "path": key,
                "size": stat.st_size,
                "time": datetime.now(timezone.utc).isoformat(),
            })
        elif current != prev:
            # Modified file
            changes.append({
                "type": "modified",
                "file": log_file.name,
                "path": key,
                "size_delta": stat.st_size - prev[1],
                "time": datetime.now(timezone.utc).isoformat(),
            })

        _file_state[key] = current

    return changes


def on_change(callback):
    """Register a callback for file changes: callback(changes: list[dict])"""
    _callbacks.append(callback)


async def watch_loop(interval: float = 2.0):
    """Async watch loop — polls for changes every `interval` seconds."""
    global _running
    _running = True
    # Initial scan to establish baseline
    scan_changes()

    while _running:
        await asyncio.sleep(interval)
        changes = scan_changes()
        if changes:
            for cb in _callbacks:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(changes)
                    else:
                        cb(changes)
                except Exception as e:
                    print(f"[watcher] callback error: {e}")


def stop():
    global _running
    _running = False


def status() -> dict:
    return {
        "running": _running,
        "tracked_files": len(_file_state),
        "callbacks": len(_callbacks),
        "log_dir": str(LOG_DIR),
    }


if __name__ == "__main__":
    from rich.console import Console
    console = Console()

    def _print_changes(changes):
        for c in changes:
            icon = "🆕" if c["type"] == "new" else "📝"
            console.print(f"  {icon} {c['file']} ({c['type']})")

    on_change(_print_changes)
    console.print(f"[bold]Watching {LOG_DIR} for changes...[/bold] (Ctrl+C to stop)")

    try:
        asyncio.run(watch_loop(interval=1.0))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
