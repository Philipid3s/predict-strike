"""
Source specs:
- AGENTS.md
- docs/agents/orchestrator.md
- docs/sessions/handoff-template.md
"""

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = REPO_ROOT / "docs" / "sessions"
ALLOWED_ROLES = {
    "orchestrator",
    "frontend-agent",
    "backend-agent",
    "docs-agent",
    "platform-agent",
    "qa-agent",
}


def _extract_prepared_by_value(markdown: str) -> str:
    match = re.search(
        r"^## Prepared By\s*\n([^\n]+)",
        markdown,
        flags=re.MULTILINE,
    )
    if not match:
        raise AssertionError("Missing '## Prepared By' section")
    return match.group(1).strip().strip("`")


class SessionHandoffContractAcceptanceTests(unittest.TestCase):
    def test_handoff_template_documents_orchestrator_prepared_by_expectation(self) -> None:
        template = (SESSIONS_DIR / "handoff-template.md").read_text(encoding="utf-8")

        expected_markers = [
            "## Prepared By",
            "usually `orchestrator`",
            "## Session Summary",
            "## Files Modified This Session",
            "## Risks / Watch Points",
        ]

        for marker in expected_markers:
            self.assertIn(
                marker,
                template,
                msg=f"docs/sessions/handoff-template.md marker missing: {marker}",
            )

    def test_handoff_files_use_valid_prepared_by_role_and_no_role_labels(self) -> None:
        handoff_paths = sorted(SESSIONS_DIR.glob("handoff-20*.md"))
        self.assertGreaterEqual(len(handoff_paths), 1, "Expected at least one dated handoff file")

        for handoff_path in handoff_paths:
            markdown = handoff_path.read_text(encoding="utf-8")
            prepared_by = _extract_prepared_by_value(markdown)

            self.assertIn(
                prepared_by,
                ALLOWED_ROLES,
                msg=f"{handoff_path.name} has invalid Prepared By role: {prepared_by}",
            )
            self.assertNotRegex(
                markdown,
                r"^Role:\s+",
                msg=f"{handoff_path.name} should not embed live session role labels",
            )
            self.assertNotIn(
                "Delegated agents must",
                markdown,
                msg=f"{handoff_path.name} appears to mix handoff content with policy text",
            )


if __name__ == "__main__":
    unittest.main()
