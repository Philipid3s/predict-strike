from pathlib import Path
import os
import unittest

from src.services.alert_pipeline import evaluate_alerts, list_alert_history


class AlertPipelineTests(unittest.TestCase):
    def test_alert_evaluation_persists_non_hold_alerts(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "alerts.db"
        if database_path.exists():
            database_path.unlink()

        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            evaluation = evaluate_alerts()
            history = list_alert_history()
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url

        self.assertIsNotNone(history.generated_at)
        self.assertIsNotNone(evaluation.evaluated_at)
        self.assertEqual(evaluation.created_count, len(evaluation.alerts))
        self.assertGreaterEqual(len(evaluation.alerts), 1)
        self.assertEqual(len(history.alerts), len(evaluation.alerts))
        self.assertTrue(all(alert.signal in {"BUY", "SELL"} for alert in evaluation.alerts))
        self.assertTrue(all(alert.status == "open" for alert in history.alerts))
        self.assertTrue(all(isinstance(alert.id, str) for alert in history.alerts))
