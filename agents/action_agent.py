"""
Action Agent — receives reasoning result, generates plan, runs HITL execution.

Edge cases handled:
  - HITL rejection dependency graph (edge case 3):
    Each step declares which prior steps it depends on via 'depends_on'.
    If a dependency was rejected or skipped, all downstream steps are
    automatically blocked — the agent will not execute them or ask for
    approval. This prevents partial fixes that leave the system in a
    worse state than doing nothing.

    Example: killing a blocking DB query (step 3) is a prerequisite for
    increasing pool size (step 4). If the SRE rejects step 3, step 4 is
    automatically blocked.

Outputs: resolution summary dict with approved/rejected/blocked counts.
"""
import os
from planner.plan import mock_plan
from hitl.controller import execute, log_decision


class ActionAgent:
    name = "ActionAgent"

    def _blocked_by(self, step: dict, rejected_steps: set[int]) -> int | None:
        """
        Returns the step number that blocks this step, or None if unblocked.
        A step is blocked if any of its declared dependencies were rejected.
        """
        for dep in step.get("depends_on", []):
            if dep in rejected_steps:
                return dep
        return None

    def run(self, signal: dict, reasoning: dict) -> dict:
        """
        Execute the remediation plan with HITL gates and dependency enforcement.
        READ_ONLY steps run automatically.
        MUTATING steps require SRE approval.
        Rejected steps propagate blocks to all dependent downstream steps.
        """
        plan = mock_plan(reasoning)
        steps = plan["plan"]
        approved = rejected = blocked = 0
        rejected_steps: set[int] = set()  # step numbers that were rejected/skipped

        print(f"[{self.name}] 📋 Plan: {len(steps)} steps ({sum(1 for s in steps if s['type'] == 'MUTATING')} need approval)")

        for step in steps:
            step_num = step["step"]

            # Edge case 3: check if a dependency was rejected — block this step
            blocker = self._blocked_by(step, rejected_steps)
            if blocker is not None:
                print(f"[{self.name}] 🚫 Step {step_num} BLOCKED — depends on rejected step {blocker}: {step['action'][:60]}")
                log_decision(signal["source"], step, f"BLOCKED_BY_STEP_{blocker}")
                rejected_steps.add(step_num)
                blocked += 1
                continue

            if step["type"] == "READ_ONLY":
                execute(step, signal["source"], auto=True)
                continue

            # MUTATING — requires human approval
            print(f"[{self.name}] ⚠  Step {step_num} [{step['risk']}]: {step['action']}")
            decision = "y" if os.getenv("AUTO_APPROVE") == "1" else input(f"[{self.name}] Approve? [y/n]: ").strip().lower()

            if decision == "y":
                execute(step, signal["source"])
                approved += 1
            else:
                log_decision(signal["source"], step, "REJECTED")
                rejected_steps.add(step_num)
                rejected += 1

        status = "RESOLVED" if rejected == 0 and blocked == 0 else "PARTIALLY_RESOLVED"
        summary = {
            "incident": signal["source"],
            "approved": approved,
            "rejected": rejected,
            "blocked": blocked,
            "status": status,
        }
        icon = "✅" if status == "RESOLVED" else "⚠️ "
        print(f"[{self.name}] {icon} {status} — approved={approved} rejected={rejected} blocked={blocked}\n")
        return summary
