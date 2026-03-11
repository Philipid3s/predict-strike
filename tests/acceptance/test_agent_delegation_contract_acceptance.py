"""
Source specs:
- AGENTS.md
- docs/agents/orchestrator.md
"""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


class AgentDelegationContractAcceptanceTests(unittest.TestCase):
    def test_agents_md_documents_single_orchestrator_native_delegation_rules(self) -> None:
        agents_md = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

        expected_markers = [
            "Exactly one active orchestrator may exist for the session.",
            "The main session is the only place allowed to use `Role: orchestrator`.",
            "Each delegated task must name the repository specialist explicitly via",
            "`assigned_to`.",
            "Each delegated task must include an `active_role` field that matches the",
            "assigned repository specialist.",
            "The delegated task message itself must not begin with",
            "`Role: orchestrator`, even if the parent orchestrator authored the handoff.",
            "Delegated agents must begin their own task output with",
            "`Role: <assigned specialist>`.",
            "Delegated agents must not present themselves as generic coordinators,",
            "orchestrators, or unlabeled workers in user-visible summaries.",
            "runtime may still use generic transport names such",
            "not valid substitutes for repository",
            "role labels in task packets, summaries, reports, or handoffs.",
        ]

        for marker in expected_markers:
            self.assertIn(
                marker,
                agents_md,
                msg=f"AGENTS.md delegation-role marker missing: {marker}",
            )

    def test_orchestrator_contract_requires_explicit_specialist_role_and_forbids_delegate_orchestrators(
        self,
    ) -> None:
        orchestrator_md = (REPO_ROOT / "docs" / "agents" / "orchestrator.md").read_text(
            encoding="utf-8"
        )

        expected_markers = [
            "Runtime agent classes such as `worker`, `default`, or similar host-provided",
            "The orchestrator must delegate to explicit repository specialists such as",
            "`frontend-agent`, `backend-agent`, `docs-agent`, `platform-agent`, or",
            "`qa-agent`, and must encode that role in the task packet.",
            "Ensure every delegated task names one repository specialist and includes an",
            "`active_role` that matches that specialist.",
            "Ensure the delegated task message itself does not begin with",
            "`Role: orchestrator`, even if the parent orchestrator authored the handoff.",
            "Ensure delegated outputs present themselves as the assigned specialist role,",
            "never as `Role: orchestrator`.",
            "Only the main session may use `Role: orchestrator`",
            "Delegated agents must use only the assigned specialist role label",
            "Delegated agents must not identify themselves as orchestrator, coordinator,",
            "Delegated task messages must not begin with `Role: orchestrator`",
            "active_role: '<same as assigned_to>'",
            "Delegating through a runtime transport label without naming the repository",
            "Beginning a delegated task message with `Role: orchestrator`",
            "Allowing delegated output to present as `Role: orchestrator`",
        ]

        for marker in expected_markers:
            self.assertIn(
                marker,
                orchestrator_md,
                msg=f"docs/agents/orchestrator.md delegation marker missing: {marker}",
            )


if __name__ == "__main__":
    unittest.main()
