from pathlib import Path
import os
import sys
import unittest

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.main import app  # noqa: E402


class AlertRouteTests(unittest.TestCase):
    def test_alert_endpoints_evaluate_and_list_history(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "alert-routes.db"
        if database_path.exists():
            database_path.unlink()

        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)

            evaluate_response = client.post("/api/v1/alerts/evaluate")
            history_response = client.get("/api/v1/alerts")
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url

        self.assertEqual(evaluate_response.status_code, 200)
        self.assertEqual(history_response.status_code, 200)

        evaluation_payload = evaluate_response.json()
        history_payload = history_response.json()

        self.assertIn("evaluated_at", evaluation_payload)
        self.assertIn("created_count", evaluation_payload)
        self.assertIn("alerts", evaluation_payload)
        self.assertIn("generated_at", history_payload)
        self.assertIn("alerts", history_payload)
        self.assertGreaterEqual(len(history_payload["alerts"]), len(evaluation_payload["alerts"]))
        self.assertTrue(all(isinstance(alert["id"], str) for alert in history_payload["alerts"]))
