from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.main import app  # noqa: E402


def _runtime_database_url(filename: str) -> str:
    runtime_dir = Path(__file__).resolve().parent / ".runtime"
    runtime_dir.mkdir(exist_ok=True)
    database_path = runtime_dir / filename
    if database_path.exists():
        database_path.unlink()
    return f"sqlite:///{database_path.as_posix()}"


class PizzaIndexRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def _set_database(self, filename: str) -> dict[str, str | None]:
        previous = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "PIZZA_INDEX_ENABLE_LIVE_PROVIDER": os.environ.get("PIZZA_INDEX_ENABLE_LIVE_PROVIDER"),
        }
        os.environ["DATABASE_URL"] = _runtime_database_url(filename)
        os.environ["PIZZA_INDEX_ENABLE_LIVE_PROVIDER"] = "true"
        return previous

    def _restore_database(self, previous: dict[str, str | None]) -> None:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_targets_endpoint_returns_registry(self) -> None:
        response = self.client.get("/api/v1/pizza-index/targets")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("generated_at", payload)
        self.assertGreaterEqual(len(payload["targets"]), 4)
        self.assertEqual(payload["targets"][0]["target_id"], "dominos_pentagon_city")

    def test_target_activity_endpoint_returns_live_shape(self) -> None:
        previous = self._set_database("pizza-index-route-activity.db")
        try:
            with patch(
                "src.services.pizza_index_pipeline.fetch_pizzint_dashboard_payload",
                return_value={
                    "success": True,
                    "data": [
                        {
                            "place_id": "ChIJI6ACK7q2t4kRFcPtFhUuYhU",
                            "name": "Domino's Pizza (Pentagon Closest)",
                            "address": "https://www.google.com/maps/place/Domino's+Pizza/@38.8627308,-77.0879692,17z/data=!3m1!4b1",
                            "current_popularity": 76,
                            "percentage_of_usual": 173.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        }
                    ],
                },
            ):
                response = self.client.get("/api/v1/pizza-index/targets/dominos_pentagon_city/activity")
        finally:
            self._restore_database(previous)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["provider"], {"pizzint", "serpapi", "stub"})
        self.assertIn(payload["provider_mode"], {"primary", "fallback", "stub"})
        self.assertIn(payload["data_quality"], {"full", "partial", "unavailable"})
        self.assertIn("capture_status", payload)

    def test_unknown_target_activity_returns_404(self) -> None:
        response = self.client.get("/api/v1/pizza-index/targets/unknown/activity")

        self.assertEqual(response.status_code, 404)

    def test_latest_and_refresh_endpoints_return_snapshot_shape(self) -> None:
        previous = self._set_database("pizza-index-route-snapshot.db")
        try:
            with patch(
                "src.services.pizza_index_pipeline.fetch_pizzint_dashboard_payload",
                return_value={
                    "success": True,
                    "data": [
                        {
                            "place_id": "ChIJI6ACK7q2t4kRFcPtFhUuYhU",
                            "name": "Domino's Pizza (Pentagon Closest)",
                            "address": "https://www.google.com/maps/place/Domino's+Pizza",
                            "current_popularity": 68,
                            "percentage_of_usual": 158.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        },
                        {
                            "place_id": "ChIJo03BaX-3t4kRbyhPM0rTuqM",
                            "name": "Papa Johns Pizza",
                            "address": "https://www.google.com/maps/place/Papa+Johns+Pizza",
                            "current_popularity": 68,
                            "percentage_of_usual": 158.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        },
                        {
                            "place_id": "ChIJS1rpOC-3t4kRsLyM6aftM8k",
                            "name": "We, The Pizza",
                            "address": "https://www.google.com/maps/place/We,+The+Pizza",
                            "current_popularity": 68,
                            "percentage_of_usual": 158.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        },
                        {
                            "place_id": "ChIJcYireCe3t4kR4d9trEbGYjc",
                            "name": "Extreme Pizza",
                            "address": "https://www.google.com/maps/place/Extreme+Pizza",
                            "current_popularity": 68,
                            "percentage_of_usual": 158.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        },
                    ],
                },
            ):
                latest_response = self.client.get("/api/v1/pizza-index/latest")
                refresh_response = self.client.post("/api/v1/pizza-index/refresh")
        finally:
            self._restore_database(previous)

        self.assertEqual(latest_response.status_code, 200)
        self.assertEqual(refresh_response.status_code, 200)

        for payload in (latest_response.json(), refresh_response.json()):
            self.assertIn("generated_at", payload)
            self.assertIn("pizza_index", payload)
            self.assertIn("pizza_index_confidence", payload)
            self.assertIn("quality_summary", payload)
            self.assertIn("targets", payload)
            self.assertGreaterEqual(payload["quality_summary"]["full_count"], 4)


if __name__ == "__main__":
    unittest.main()
