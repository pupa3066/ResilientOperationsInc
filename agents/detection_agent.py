"""
Detection Agent — watches incident logs and fires when anomalies are found.
Owns: observation layer. Outputs: incident signal dict.
"""
from observation.log_reader import load_signals

class DetectionAgent:
    name = "DetectionAgent"

    def run(self) -> list[dict]:
        signals = load_signals()
        fired = []
        for s in signals:
            if s["signal_count"] > 0:
                print(f"[{self.name}] 🔴 Incident detected: {s['source']} ({s['signal_count']} signals) → services: {', '.join(s['services'])}")
                fired.append(s)
        return fired
