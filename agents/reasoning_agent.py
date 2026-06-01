"""
Reasoning Agent — receives signals from DetectionAgent, runs Gemini analysis.
Owns: root cause, hypothesis tree, blast radius. Outputs: reasoning result dict.
"""
import os
from reasoning.reason import mock_reason, reason

class ReasoningAgent:
    name = "ReasoningAgent"

    def run(self, signal: dict) -> dict:
        if os.getenv("MOCK_GEMINI") == "1":
            result = mock_reason(signal)
        else:
            try:
                result = reason(signal)
            except Exception as e:
                print(f"[{self.name}] ⚠ Gemini failed ({e}), falling back to mock")
                result = mock_reason(signal)
        print(f"[{self.name}] 🧠 Root cause ({result['confidence_pct']}%): {result['root_cause']}")
        print(f"[{self.name}]    Blast radius: {', '.join(result['blast_radius'])}")
        return result
