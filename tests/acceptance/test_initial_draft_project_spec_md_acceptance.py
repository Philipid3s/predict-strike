"""
Source spec: docs/specs/initial-draft-project-spec.md
"""

import os
from pathlib import Path
import sqlite3
import sys
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from src.main import app  # noqa: E402


class InitialDraftProjectSpecMdAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_risk_score_endpoint_returns_explainable_model_output(self) -> None:
        response = self.client.post(
            "/api/v1/risk/score",
            json={
                "features": {
                    "flight_anomaly": 0.68,
                    "notam_spike": 0.34,
                    "satellite_buildup": 0.21,
                    "news_volume": 0.57,
                    "osint_activity": 0.46,
                    "pizza_index": 0.12,
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("score", payload)
        self.assertIn("classification", payload)
        self.assertIn("breakdown", payload)
        self.assertIn("thresholds", payload)
        self.assertEqual(len(payload["breakdown"]), 6)
        self.assertEqual(payload["thresholds"], {"watch": 0.4, "alert": 0.65})

    def test_market_opportunities_endpoint_returns_comparison_signals(self) -> None:
        response = self.client.get("/api/v1/markets/opportunities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("generated_at", payload)
        self.assertGreaterEqual(len(payload["opportunities"]), 1)
        first = payload["opportunities"][0]
        self.assertIn("market_probability", first)
        self.assertIn("model_probability", first)
        self.assertIn(first["signal"], {"BUY", "HOLD", "SELL"})

    def test_market_ingestion_persists_polymarket_observation(self) -> None:
        original_database_url = os.environ.get("DATABASE_URL")
        database_path = (
            REPO_ROOT / "tests" / "acceptance" / f"acceptance-markets-{uuid4().hex}.db"
        )
        try:
            os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

            response = self.client.get("/api/v1/markets/opportunities")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertGreaterEqual(len(payload["opportunities"]), 1)
            first = payload["opportunities"][0]
            self.assertTrue(first["question"])
            self.assertGreaterEqual(first["market_probability"], 0.0)
            self.assertLessEqual(first["market_probability"], 1.0)

            with sqlite3.connect(str(database_path)) as connection:
                source_names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT DISTINCT source_name FROM source_observations"
                    ).fetchall()
                }

            self.assertIn("Polymarket", source_names)
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url
            if database_path.exists():
                try:
                    database_path.unlink()
                except PermissionError:
                    pass

    def test_signal_pipeline_stores_raw_observations_separately_from_snapshots(self) -> None:
        original_database_url = os.environ.get("DATABASE_URL")
        database_path = (
            REPO_ROOT / "tests" / "acceptance" / f"acceptance-signals-{uuid4().hex}.db"
        )
        try:
            os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

            response = self.client.get("/api/v1/signals/latest")

            self.assertEqual(response.status_code, 200)
            self.assertTrue(database_path.exists())

            with sqlite3.connect(str(database_path)) as connection:
                observation_count = connection.execute(
                    "SELECT COUNT(*) FROM source_observations"
                ).fetchone()[0]
                snapshot_count = connection.execute(
                    "SELECT COUNT(*) FROM signal_snapshots"
                ).fetchone()[0]

            self.assertGreaterEqual(observation_count, 1)
            self.assertGreaterEqual(snapshot_count, 1)
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url
            if database_path.exists():
                try:
                    database_path.unlink()
                except PermissionError:
                    pass

    def test_signal_snapshot_includes_news_monitoring_output(self) -> None:
        original_database_url = os.environ.get("DATABASE_URL")
        database_path = (
            REPO_ROOT / "tests" / "acceptance" / f"acceptance-news-{uuid4().hex}.db"
        )
        try:
            os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

            response = self.client.get("/api/v1/signals/latest")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("features", payload)
            self.assertIn("news_volume", payload["features"])
            self.assertGreater(payload["features"]["news_volume"], 0.0)
            self.assertIn("GDELT", {source["name"] for source in payload["sources"]})
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url
            if database_path.exists():
                try:
                    database_path.unlink()
                except PermissionError:
                    pass

    def test_pizza_index_contract_is_available(self) -> None:
        targets_response = self.client.get("/api/v1/pizza-index/targets")
        latest_response = self.client.get("/api/v1/pizza-index/latest")

        self.assertEqual(targets_response.status_code, 200)
        self.assertEqual(latest_response.status_code, 200)

        targets_payload = targets_response.json()
        latest_payload = latest_response.json()

        self.assertGreaterEqual(len(targets_payload["targets"]), 1)
        self.assertIn("pizza_index", latest_payload)
        self.assertIn("pizza_index_confidence", latest_payload)

    def test_signal_snapshot_uses_pizza_index_activity_placeholder_name(self) -> None:
        response = self.client.get("/api/v1/signals/latest")

        self.assertEqual(response.status_code, 200)
        source_names = {source["name"] for source in response.json()["sources"]}
        self.assertIn("Pizza Index Activity", source_names)
        self.assertNotIn("Behavioral Signals", source_names)


if __name__ == "__main__":
    unittest.main()

