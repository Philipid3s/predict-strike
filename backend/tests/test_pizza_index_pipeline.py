from pathlib import Path
import os
import unittest
from unittest.mock import patch

from src.services.pizza_index_pipeline import (
    build_latest_snapshot,
    get_target_activity,
    list_targets,
    refresh_snapshot,
)
from src.storage.signal_store import SignalStore


def _runtime_database_url(filename: str) -> str:
    runtime_dir = Path(__file__).resolve().parent / ".runtime"
    runtime_dir.mkdir(exist_ok=True)
    database_path = runtime_dir / filename
    if database_path.exists():
        database_path.unlink()
    return f"sqlite:///{database_path.as_posix()}"


class PizzaIndexPipelineTests(unittest.TestCase):
    def _set_env(self, *, database_url: str, serpapi_key: str | None = None, daily_limit: str | None = None) -> dict[str, str | None]:
        previous = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "SERPAPI_API_KEY": os.environ.get("SERPAPI_API_KEY"),
            "SERPAPI_DAILY_LIMIT": os.environ.get("SERPAPI_DAILY_LIMIT"),
            "PIZZA_INDEX_ENABLE_LIVE_PROVIDER": os.environ.get("PIZZA_INDEX_ENABLE_LIVE_PROVIDER"),
        }
        os.environ["DATABASE_URL"] = database_url
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

    def test_targets_registry_returns_monitored_places(self) -> None:
        response = list_targets()

        self.assertGreaterEqual(len(response.targets), 4)
        self.assertEqual(response.targets[0].target_id, "dominos_pentagon_city")
        self.assertTrue(all(target.active for target in response.targets))
        self.assertIn("google.com/maps/place/Domino", response.targets[0].google_maps_url)

    def test_target_activity_uses_pizzint_primary_when_busyness_is_extracted(self) -> None:
        database_url = _runtime_database_url("pizza-index-pizzint.db")
        previous = self._set_env(database_url=database_url)
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
                            "current_popularity": 78,
                            "percentage_of_usual": 173.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        }
                    ],
                },
            ):
                activity = get_target_activity("dominos_pentagon_city")
        finally:
            self._restore_env(previous)

        self.assertIsNotNone(activity)
        assert activity is not None
        self.assertEqual(activity.provider, "pizzint")
        self.assertEqual(activity.provider_mode, "primary")
        self.assertEqual(activity.data_quality, "full")
        self.assertEqual(activity.current_busyness_percent, 78)
        self.assertEqual(activity.busyness_delta_percent, 33)
        self.assertIn("google.com/maps/place/Domino", activity.google_maps_url)
        store = SignalStore(database_url)
        latest_payload = store.get_latest_pizza_index_provider_payload(
            target_id="dominos_pentagon_city",
            provider="pizzint",
        )
        self.assertIsNotNone(latest_payload)
        assert latest_payload is not None
        self.assertEqual(latest_payload["current_busyness_percent"], 78)

    def test_target_activity_falls_back_to_serpapi_when_pizzint_fails(self) -> None:
        database_url = _runtime_database_url("pizza-index-serpapi.db")
        previous = self._set_env(database_url=database_url, serpapi_key="test-key")
        try:
            with patch(
                "src.services.pizza_index_pipeline.fetch_pizzint_dashboard_payload",
                side_effect=RuntimeError("upstream unavailable"),
            ), patch(
                "src.services.pizza_index_pipeline.fetch_serpapi_place_payload",
                return_value={
                    "current_busyness_percent": 64,
                    "usual_busyness_percent": 40,
                    "busyness_delta_percent": 24,
                    "current_busyness_label": "busier_than_usual",
                    "rating": 4.0,
                    "reviews_count": 500,
                    "address": "Pentagon City, Arlington, VA",
                    "is_open": True,
                    "capture_status": "serpapi_google_maps_ok",
                },
            ):
                activity = get_target_activity("dominos_pentagon_city")
        finally:
            self._restore_env(previous)

        self.assertIsNotNone(activity)
        assert activity is not None
        self.assertEqual(activity.provider, "serpapi")
        self.assertEqual(activity.provider_mode, "fallback")
        self.assertEqual(activity.data_quality, "full")
        self.assertEqual(activity.current_busyness_percent, 64)
        store = SignalStore(database_url)
        latest_payload = store.get_latest_pizza_index_provider_payload(
            target_id="dominos_pentagon_city",
            provider="serpapi",
        )
        self.assertIsNotNone(latest_payload)
        assert latest_payload is not None
        self.assertEqual(latest_payload["current_busyness_percent"], 64)

    def test_target_activity_keeps_partial_pizzint_data_instead_of_stub(self) -> None:
        database_url = _runtime_database_url("pizza-index-pizzint-partial.db")
        previous = self._set_env(database_url=database_url)
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
                            "current_popularity": None,
                            "percentage_of_usual": None,
                            "is_closed_now": True,
                            "baseline_popular_times": {},
                        }
                    ],
                },
            ):
                activity = get_target_activity("dominos_pentagon_city")
        finally:
            self._restore_env(previous)

        self.assertIsNotNone(activity)
        assert activity is not None
        self.assertEqual(activity.provider, "pizzint")
        self.assertEqual(activity.provider_mode, "primary")
        self.assertEqual(activity.data_quality, "full")
        self.assertIn("google.com/maps/place/Domino", activity.google_maps_url)
        self.assertEqual(activity.current_busyness_label, "closed")

    def test_target_activity_returns_unavailable_stub_when_pizzint_only_has_link(self) -> None:
        database_url = _runtime_database_url("pizza-index-pizzint-secondary.db")
        previous = self._set_env(database_url=database_url)
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
                            "current_popularity": None,
                            "percentage_of_usual": None,
                            "is_closed_now": None,
                            "baseline_popular_times": {},
                        }
                    ],
                },
            ):
                activity = get_target_activity("dominos_pentagon_city")
        finally:
            self._restore_env(previous)

        self.assertIsNotNone(activity)
        assert activity is not None
        self.assertEqual(activity.provider, "stub")
        self.assertEqual(activity.data_quality, "unavailable")
        self.assertIsNone(activity.current_busyness_percent)

    def test_quota_exhaustion_skips_serpapi_after_daily_limit(self) -> None:
        database_url = _runtime_database_url("pizza-index-quota.db")
        previous = self._set_env(
            database_url=database_url,
            serpapi_key="test-key",
            daily_limit="1",
        )
        try:
            with patch(
                "src.services.pizza_index_pipeline.fetch_pizzint_dashboard_payload",
                side_effect=RuntimeError("upstream unavailable"),
            ), patch(
                "src.services.pizza_index_pipeline.fetch_serpapi_place_payload",
                return_value={
                    "current_busyness_percent": 71,
                    "usual_busyness_percent": 44,
                    "busyness_delta_percent": 27,
                    "current_busyness_label": "busier_than_usual",
                    "address": "Pentagon City, Arlington, VA",
                    "is_open": True,
                    "capture_status": "serpapi_google_maps_ok",
                },
            ) as serpapi_mock:
                first_activity = get_target_activity("dominos_pentagon_city")
                second_activity = get_target_activity("papa_johns_pentagon_city")

            store = SignalStore(database_url)
            usage_count = store.get_provider_daily_usage(
                "serpapi",
                first_activity.collected_at.date(),
            )
        finally:
            self._restore_env(previous)

        self.assertEqual(first_activity.provider, "serpapi")
        self.assertEqual(second_activity.provider, "stub")
        self.assertEqual(second_activity.data_quality, "unavailable")
        self.assertIn("serpapi_daily_budget_exhausted", second_activity.capture_status)
        self.assertEqual(serpapi_mock.call_count, 1)
        self.assertEqual(usage_count, 1)

    def test_latest_snapshot_aggregates_valid_shape(self) -> None:
        previous = self._set_env(database_url=_runtime_database_url("pizza-index-snapshot.db"))
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
                            "current_popularity": 70,
                            "percentage_of_usual": 156.0,
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
                            "current_popularity": 66,
                            "percentage_of_usual": 150.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        },
                        {
                            "place_id": "ChIJcYireCe3t4kR4d9trEbGYjc",
                            "name": "Extreme Pizza",
                            "address": "https://www.google.com/maps/place/Extreme+Pizza",
                            "current_popularity": 64,
                            "percentage_of_usual": 145.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        },
                    ],
                },
            ):
                snapshot = build_latest_snapshot()
        finally:
            self._restore_env(previous)

        self.assertGreater(snapshot.pizza_index, 0.0)
        self.assertGreater(snapshot.pizza_index_confidence, 0.0)
        self.assertGreaterEqual(snapshot.quality_summary.full_count, 4)
        self.assertTrue(all(target.provider in {"pizzint", "stub"} for target in snapshot.targets))

    def test_refresh_snapshot_preserves_upstream_failure_reason(self) -> None:
        previous = self._set_env(database_url=_runtime_database_url("pizza-index-upstream-failure.db"))
        try:
            with patch(
                "src.services.pizza_index_pipeline.fetch_pizzint_dashboard_payload",
                side_effect=RuntimeError("upstream unavailable"),
            ):
                snapshot = refresh_snapshot()
                activity = get_target_activity("dominos_pentagon_city")
        finally:
            self._restore_env(previous)

        self.assertEqual(snapshot.quality_summary.unavailable_count, len(snapshot.targets))
        self.assertIsNotNone(activity)
        assert activity is not None
        self.assertEqual(activity.provider, "stub")
        self.assertIn("pizzint_failed:upstream unavailable", activity.capture_status)


if __name__ == "__main__":
    unittest.main()
