"""
Action Agent — receives reasoning result, generates plan, runs HITL execution.
Owns: planner + HITL gate + audit log. Outputs: resolution summary.
"""
import os
from planner.plan import mock_plan
from hitl.controller import execute, log_decision

class ActionAgent:
    name = "ActionAgent"

    def run(self, signal: dict, reasoning: dict) -> dict:
        plan = mock_plan(reasoning)
        steps = plan["plan"]
        approved = rejected = 0

        print(f"[{self.name}] 📋 Plan: {len(steps)} steps ({sum(1 for s in steps if s['type']=='MUTATING')} need approval)")

        for step in steps:
            if step["type"] == "READ_ONLY":
                execute(step, signal["source"], auto=True)
                continue

            print(f"[{self.name}] ⚠  Step {step['step']} [{step['risk']}]: {step['action']}")
            decision = "y" if os.getenv("AUTO_APPROVE") == "1" else input(f"[{self.name}] Approve? [y/n]: ").strip().lower()

            if decision == "y":
                execute(step, signal["source"])
                approved += 1
            else:
                log_decision(signal["source"], step, "REJECTED")
                rejected += 1

        summary = {"incident": signal["source"], "approved": approved, "rejected": rejected, "status": "RESOLVED"}
        print(f"[{self.name}] ✅ {summary['status']} — approved={approved} rejected={rejected}\n")
        return summary
