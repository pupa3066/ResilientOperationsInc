"""
Detection Agent — watches incident logs and fires when anomalies are found.

Edge cases handled:
  - False positive prevention: requires MIN_SIGNALS threshold before firing.
    A single transient error will not trigger the full pipeline.
  - Cooldown: same incident source cannot re-fire within COOLDOWN_SECONDS.
    Prevents alert storms from hammering the reasoning layer.
  - Deduplication: tracks fired sources so repeated runs don't double-process.

Outputs: list of incident signal dicts → passed to ReasoningAgent.
"""
from datetime import datetime, timezone
from observation.log_reader import load_signals

# Minimum error signals required before treating as a real incident
MIN_SIGNALS = 5

# Seconds before the same source can fire again
COOLDOWN_SECONDS = 60


class DetectionAgent:
    name = "DetectionAgent"

    def __init__(self):
        # source -> last fired UTC timestamp
        self._cooldowns: dict[str, datetime] = {}

    def _in_cooldown(self, source: str) -> bool:
        last = self._cooldowns.get(source)
        if not last:
            return False
        return (datetime.now(timezone.utc) - last).total_seconds() < COOLDOWN_SECONDS

    def run(self) -> list[dict]:
        """
        Load signals from all incident logs.
        Returns only those that exceed the signal threshold and are not in cooldown.
        """
        signals = load_signals()
        fired = []

        for s in signals:
            source = s["source"]

            # Edge case 2: false positive guard — ignore low-signal noise
            if s["signal_count"] < MIN_SIGNALS:
                print(f"[{self.name}] ⚪ {source} — {s['signal_count']} signals below threshold={MIN_SIGNALS}, suppressed (false positive guard)")
                continue

            # Edge case 2: cooldown — don't re-fire same source within window
            if self._in_cooldown(source):
                print(f"[{self.name}] 🟡 {source} — cooldown active, suppressed duplicate fire")
                continue

            self._cooldowns[source] = datetime.now(timezone.utc)
            print(f"[{self.name}] 🔴 Incident detected: {source} ({s['signal_count']} signals) → services: {', '.join(s['services'])}")
            fired.append(s)

        return fired
