"""
Source specs:
- docs/specs/initial-draft-project-spec.md
- docs/api/openapi.yml
"""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


class OperatorDashboardUiAcceptanceTests(unittest.TestCase):
    def test_dashboard_declares_requested_operator_sections(self) -> None:
        app_source = (REPO_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        expected_markers = [
            "Operator Dashboard",
            'aria-label="Main indicators"',
            "Per-Source Status",
            "Data mode:",
            "Alert History",
            "Polymarket Opportunities",
            "Source ",
            "Refresh Signals",
            "Evaluate Alerts",
        ]

        for marker in expected_markers:
            self.assertIn(
                marker,
                app_source,
                msg=f"Dashboard UI marker missing from frontend/src/App.tsx: {marker}",
            )

    def test_dashboard_api_client_targets_documented_endpoints(self) -> None:
        api_source = (REPO_ROOT / "frontend" / "src" / "services" / "api.ts").read_text(
            encoding="utf-8"
        )

        expected_paths = [
            "/api/v1/signals/latest",
            "/api/v1/signals/refresh",
            "/api/v1/risk/score",
            "/api/v1/markets/opportunities",
            "/api/v1/alerts",
            "/api/v1/alerts/evaluate",
        ]

        for path in expected_paths:
            self.assertIn(
                path,
                api_source,
                msg=f"Documented dashboard API path missing from frontend client: {path}",
            )

    def test_frontend_dashboard_test_covers_alert_evaluation_flow(self) -> None:
        test_source = (REPO_ROOT / "frontend" / "src" / "App.test.tsx").read_text(
            encoding="utf-8"
        )

        expected_markers = [
            "/api/v1/alerts/evaluate",
            "Evaluate Alerts",
            "created 1 new alert",
            "No alerts recorded yet",
            "Data mode: Live",
            "mode: 'fallback'",
            "Static Baseline",
            "Data mode: Static Baseline",
        ]

        for marker in expected_markers:
            self.assertIn(
                marker,
                test_source,
                msg=f"Frontend dashboard test coverage marker missing: {marker}",
            )


if __name__ == "__main__":
    unittest.main()
