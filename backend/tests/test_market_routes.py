from pathlib import Path
import os
import sqlite3
import sys
import unittest

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.main import app  # noqa: E402


class MarketRouteTests(unittest.TestCase):
    def test_opportunities_endpoint_returns_payload_and_persists_observation(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "markets-route.db"
        if database_path.exists():
            database_path.unlink()

        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)
            response = client.get("/api/v1/markets/opportunities")

            with sqlite3.connect(str(database_path)) as connection:
                observation_count = connection.execute(
                    "SELECT COUNT(*) FROM source_observations"
                ).fetchone()[0]
                polymarket_count = connection.execute(
                    "SELECT COUNT(*) FROM source_observations WHERE source_name = 'Polymarket'"
                ).fetchone()[0]
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url

        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertIn("generated_at", payload)
        self.assertEqual(payload["source"]["name"], "Polymarket")
        self.assertIn(payload["source"]["status"], {"active", "degraded"})
        self.assertIn(payload["source"]["mode"], {"live", "fallback"})
        self.assertIn(payload["upstream"], {"gamma", "pizzint", "bootstrap"})
        self.assertGreaterEqual(len(payload["opportunities"]), 1)
        self.assertIn("market_id", payload["opportunities"][0])
        self.assertIn("question", payload["opportunities"][0])
        self.assertIn("market_probability", payload["opportunities"][0])
        self.assertIn("model_probability", payload["opportunities"][0])
        self.assertIn("edge", payload["opportunities"][0])
        self.assertIn("signal", payload["opportunities"][0])
        self.assertGreaterEqual(observation_count, 4)
        self.assertEqual(polymarket_count, 1)


if __name__ == "__main__":
    unittest.main()
