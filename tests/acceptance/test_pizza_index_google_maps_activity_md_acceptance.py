"""
Source spec: docs/specs/pizza-index-google-maps-activity.md
"""

from datetime import date
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from src.main import app  # noqa: E402
from src.storage.signal_store import SignalStore  # noqa: E402


def _runtime_database_url(filename: str) -> str:
    database_path = REPO_ROOT / "tests" / "acceptance" / filename
    if database_path.exists():
        database_path.unlink()
    return f"sqlite:///{database_path.as_posix()}"


class PizzaIndexGoogleMapsActivityMdAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def _set_env(
        self,
        *,
        database_name: str,
        serpapi_key: str | None = None,
        daily_limit: str | None = None,
    ) -> dict[str, str | None]:
        previous = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "SERPAPI_API_KEY": os.environ.get("SERPAPI_API_KEY"),
            "SERPAPI_DAILY_LIMIT": os.environ.get("SERPAPI_DAILY_LIMIT"),
            "PIZZA_INDEX_ENABLE_LIVE_PROVIDER": os.environ.get("PIZZA_INDEX_ENABLE_LIVE_PROVIDER"),
        }
        os.environ["DATABASE_URL"] = _runtime_database_url(database_name)
        os.environ["PIZZA_INDEX_ENABLE_LIVE_PROVIDER"] = "true"
        if serpapi_key is None:
            os.environ.pop("SERPAPI_API_KEY", None)
        else:
            os.environ["SERPAPI_API_KEY"] = serpapi_key
        if daily_limit is None:
            os.environ.pop("SERPAPI_DAILY_LIMIT", None)
        else:
            os.environ["SERPAPI_DAILY_LIMIT"] = daily_limit
        return previous

    def _restore_env(self, previous: dict[str, str | None]) -> None:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_target_registry_exposes_current_monitored_pizza_places(self) -> None:
        response = self.client.get("/api/v1/pizza-index/targets")

        self.assertEqual(response.status_code, 200)
        target_ids = [target["target_id"] for target in response.json()["targets"]]
        self.assertEqual(
            target_ids,
            [
                "dominos_pentagon_city",
                "papa_johns_pentagon_city",
                "we_the_pizza_pentagon_row",
                "extreme_pizza_pentagon_row",
                "wiseguy_pizza_rosslyn",
            ],
        )

    def test_primary_provider_path_returns_full_activity_when_busyness_exists(self) -> None:
        previous = self._set_env(database_name="acceptance-pizza-pizzint.db")
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
                            "current_popularity": 81,
                            "percentage_of_usual": 172.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        }
                    ],
                },
            ):
                response = self.client.get("/api/v1/pizza-index/targets/dominos_pentagon_city/activity")
        finally:
            self._restore_env(previous)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "pizzint")
        self.assertEqual(payload["provider_mode"], "primary")
        self.assertEqual(payload["data_quality"], "full")
        self.assertEqual(payload["busyness_delta_percent"], 34)
        self.assertIn("google.com/maps/place/Domino", payload["google_maps_url"])

    def test_raw_provider_payload_is_persisted_for_auditing(self) -> None:
        database_url = _runtime_database_url("acceptance-pizza-provider-payload.db")
        previous = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "PIZZA_INDEX_ENABLE_LIVE_PROVIDER": os.environ.get("PIZZA_INDEX_ENABLE_LIVE_PROVIDER"),
        }
        os.environ["DATABASE_URL"] = database_url
        os.environ["PIZZA_INDEX_ENABLE_LIVE_PROVIDER"] = "true"
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
                            "current_popularity": 75,
                            "percentage_of_usual": 163.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                            "debug": {"source": "pizzint"},
                        }
                    ],
                },
            ):
                response = self.client.get("/api/v1/pizza-index/targets/dominos_pentagon_city/activity")

            payload_store = SignalStore(database_url)
            raw_payload = payload_store.get_latest_pizza_index_provider_payload(
                target_id="dominos_pentagon_city",
                provider="pizzint",
            )
        finally:
            self._restore_env(previous)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(raw_payload)
        assert raw_payload is not None
        self.assertEqual(raw_payload["capture_status"], "pizzint_dashboard_ok")
        self.assertIn("debug", raw_payload)

    def test_fallback_provider_path_uses_serpapi_when_primary_fails(self) -> None:
        previous = self._set_env(
            database_name="acceptance-pizza-serpapi.db",
            serpapi_key="test-key",
            daily_limit="4",
        )
        try:
            with patch(
                "src.services.pizza_index_pipeline.fetch_pizzint_dashboard_payload",
                side_effect=RuntimeError("upstream unavailable"),
            ), patch(
                "src.services.pizza_index_pipeline.fetch_serpapi_place_payload",
                return_value={
                    "current_busyness_percent": 61,
                    "usual_busyness_percent": 45,
                    "busyness_delta_percent": 16,
                    "current_busyness_label": "busier_than_usual",
                    "address": "Pentagon City, Arlington, VA",
                    "is_open": True,
                    "capture_status": "serpapi_google_maps_ok",
                },
            ):
                response = self.client.get("/api/v1/pizza-index/targets/dominos_pentagon_city/activity")
        finally:
            self._restore_env(previous)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "serpapi")
        self.assertEqual(payload["provider_mode"], "fallback")
        self.assertIn(payload["data_quality"], {"full", "partial"})

    def test_serpapi_daily_budget_is_hard_capped(self) -> None:
        database_url = _runtime_database_url("acceptance-pizza-serpapi-budget.db")
        previous = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "SERPAPI_API_KEY": os.environ.get("SERPAPI_API_KEY"),
            "SERPAPI_DAILY_LIMIT": os.environ.get("SERPAPI_DAILY_LIMIT"),
            "PIZZA_INDEX_ENABLE_LIVE_PROVIDER": os.environ.get("PIZZA_INDEX_ENABLE_LIVE_PROVIDER"),
        }
        os.environ["DATABASE_URL"] = database_url
        os.environ["SERPAPI_API_KEY"] = "test-key"
        os.environ["SERPAPI_DAILY_LIMIT"] = "1"
        os.environ["PIZZA_INDEX_ENABLE_LIVE_PROVIDER"] = "true"
        try:
            with patch(
                "src.services.pizza_index_pipeline.fetch_pizzint_dashboard_payload",
                side_effect=RuntimeError("upstream unavailable"),
            ), patch(
                "src.services.pizza_index_pipeline.fetch_serpapi_place_payload",
                return_value={
                    "current_busyness_percent": 61,
                    "usual_busyness_percent": 45,
                    "busyness_delta_percent": 16,
                    "current_busyness_label": "busier_than_usual",
                    "address": "Pentagon City, Arlington, VA",
                    "is_open": True,
                    "capture_status": "serpapi_google_maps_ok",
                },
            ) as serpapi_mock:
                first = self.client.get("/api/v1/pizza-index/targets/dominos_pentagon_city/activity")
                second = self.client.get("/api/v1/pizza-index/targets/papa_johns_pentagon_city/activity")

            first_payload = first.json()
            second_payload = second.json()
            store = SignalStore(database_url)
            usage = store.get_provider_daily_usage(
                "serpapi",
                date.fromisoformat(first_payload["collected_at"][:10]),
            )
        finally:
            self._restore_env(previous)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first_payload["provider"], "serpapi")
        self.assertEqual(second_payload["provider"], "stub")
        self.assertEqual(second_payload["data_quality"], "unavailable")
        self.assertIn("serpapi_daily_budget_exhausted", second_payload["capture_status"])
        self.assertEqual(serpapi_mock.call_count, 1)
        self.assertEqual(usage, 1)


if __name__ == "__main__":
    unittest.main()
