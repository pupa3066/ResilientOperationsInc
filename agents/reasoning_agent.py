"""
Reasoning Agent — receives signals from DetectionAgent, runs Gemini analysis.
Owns: root cause, hypothesis tree, blast radius. Outputs: reasoning result dict.
"""
import os
from reasoning.reason import mock_reason

class ReasoningAgent:
    name = "ReasoningAgent"

    def run(self, signal: dict) -> dict:
        result = mock_reason(signal)
        print(f"[{self.name}] 🧠 Root cause ({result['confidence_pct']}%): {result['root_cause']}")
        print(f"[{self.name}]    Blast radius: {', '.join(result['blast_radius'])}")
        return result
