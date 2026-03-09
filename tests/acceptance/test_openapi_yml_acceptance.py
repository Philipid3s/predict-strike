"""
Source spec: docs/api/openapi.yml
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


class OpenApiYmlAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_documented_routes_exist(self) -> None:
        checks = {
            ("GET", "/health"): 200,
            ("GET", "/api/v1/signals/latest"): 200,
            ("POST", "/api/v1/signals/refresh"): 200,
            ("GET", "/api/v1/pizza-index/targets"): 200,
            ("GET", "/api/v1/pizza-index/targets/dominos_pentagon_city/activity"): 200,
            ("GET", "/api/v1/pizza-index/latest"): 200,
            ("POST", "/api/v1/pizza-index/refresh"): 200,
            ("POST", "/api/v1/risk/score"): 422,
            ("GET", "/api/v1/markets/opportunities"): 200,
            ("GET", "/api/v1/alerts"): 200,
            ("POST", "/api/v1/alerts/evaluate"): 200,
        }

        for (method, path), expected_status in checks.items():
            response = self.client.request(method, path)
            self.assertEqual(response.status_code, expected_status, msg=f"{method} {path}")

    def test_signal_snapshot_matches_documented_source_schema(self) -> None:
        response = self.client.get("/api/v1/signals/latest")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("sources", payload)

        for source in payload["sources"]:
            self.assertEqual(
                set(source.keys()),
                {"name", "status", "mode", "last_checked_at"},
                msg="Signal source fields drift from docs/api/openapi.yml",
            )
            self.assertIn(
                source["status"],
                {"planned", "active", "degraded"},
                msg="Signal source status drift from docs/api/openapi.yml",
            )
            self.assertIn(
                source["mode"],
                {"live", "fallback", "static_baseline"},
                msg="Signal source mode drift from docs/api/openapi.yml",
            )

    def test_market_opportunities_matches_documented_source_schema(self) -> None:
        response = self.client.get("/api/v1/markets/opportunities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload.keys()),
            {"generated_at", "source", "upstream", "opportunities"},
            msg="Market opportunities response keys drift from docs/api/openapi.yml",
        )
        self.assertEqual(
            set(payload["source"].keys()),
            {"name", "status", "mode", "last_checked_at"},
            msg="Market opportunities source fields drift from docs/api/openapi.yml",
        )
        self.assertIn(
            payload["source"]["mode"],
            {"live", "fallback", "static_baseline"},
            msg="Market opportunities source mode drift from docs/api/openapi.yml",
        )
        self.assertIn(
            payload["upstream"],
            {"gamma", "pizzint", "bootstrap"},
            msg="Market opportunities upstream drift from docs/api/openapi.yml",
        )

    def test_pizza_index_targets_matches_documented_schema(self) -> None:
        response = self.client.get("/api/v1/pizza-index/targets")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload.keys()),
            {"generated_at", "targets"},
            msg="Pizza index targets response keys drift from docs/api/openapi.yml",
        )
        self.assertGreaterEqual(len(payload["targets"]), 1)
        first = payload["targets"][0]
        self.assertEqual(
            set(first.keys()),
            {
                "target_id",
                "display_name",
                "category",
                "priority_weight",
                "location_cluster",
                "google_maps_url",
                "active",
            },
            msg="Pizza index target fields drift from docs/api/openapi.yml",
        )

    def test_pizza_index_target_activity_matches_documented_schema(self) -> None:
        response = self.client.get("/api/v1/pizza-index/targets/dominos_pentagon_city/activity")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload.keys()),
            {
                "target_id",
                "display_name",
                "provider",
                "provider_mode",
                "collected_at",
                "data_quality",
                "capture_status",
                "is_open",
                "current_busyness_percent",
                "usual_busyness_percent",
                "busyness_delta_percent",
                "current_busyness_label",
                "rating",
                "reviews_count",
                "address",
                "google_maps_url",
            },
            msg="Pizza index activity fields drift from docs/api/openapi.yml",
        )
        self.assertIn(payload["provider"], {"pizzint", "serpapi", "stub"})
        self.assertIn(payload["provider_mode"], {"primary", "fallback", "stub"})
        self.assertIn(payload["data_quality"], {"full", "partial", "unavailable"})
        self.assertIn("google.com/maps/place/", payload["google_maps_url"])

    def test_pizza_index_snapshot_matches_documented_schema(self) -> None:
        response = self.client.get("/api/v1/pizza-index/latest")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload.keys()),
            {"generated_at", "pizza_index", "pizza_index_confidence", "quality_summary", "targets"},
            msg="Pizza index snapshot response keys drift from docs/api/openapi.yml",
        )
        self.assertEqual(
            set(payload["quality_summary"].keys()),
            {"full_count", "partial_count", "unavailable_count"},
            msg="Pizza index quality summary fields drift from docs/api/openapi.yml",
        )

    def test_refresh_endpoint_returns_documented_snapshot_shape_and_persists(self) -> None:
        original_database_url = os.environ.get("DATABASE_URL")
        database_path = (
            REPO_ROOT / "tests" / "acceptance" / f"acceptance-refresh-{uuid4().hex}.db"
        )
        try:
            os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

            latest_response = self.client.get("/api/v1/signals/latest")
            self.assertEqual(latest_response.status_code, 200)

            with sqlite3.connect(str(database_path)) as connection:
                initial_observation_count = connection.execute(
                    "SELECT COUNT(*) FROM source_observations"
                ).fetchone()[0]
                initial_snapshot_count = connection.execute(
                    "SELECT COUNT(*) FROM signal_snapshots"
                ).fetchone()[0]

            refresh_response = self.client.post("/api/v1/signals/refresh")

            self.assertEqual(refresh_response.status_code, 200)

            payload = refresh_response.json()
            self.assertIn("generated_at", payload)
            self.assertIn("region_focus", payload)
            self.assertIn("features", payload)
            self.assertIn("sources", payload)

            with sqlite3.connect(str(database_path)) as connection:
                refreshed_observation_count = connection.execute(
                    "SELECT COUNT(*) FROM source_observations"
                ).fetchone()[0]
                refreshed_snapshot_count = connection.execute(
                    "SELECT COUNT(*) FROM signal_snapshots"
                ).fetchone()[0]

            self.assertGreaterEqual(initial_observation_count, 1)
            self.assertEqual(initial_snapshot_count, 1)
            self.assertGreater(refreshed_observation_count, initial_observation_count)
            self.assertEqual(refreshed_snapshot_count, initial_snapshot_count + 1)
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

    def test_alert_history_matches_documented_schema(self) -> None:
        original_database_url = os.environ.get("DATABASE_URL")
        database_path = (
            REPO_ROOT / "tests" / "acceptance" / f"acceptance-alert-history-{uuid4().hex}.db"
        )
        try:
            os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

            evaluation_response = self.client.post("/api/v1/alerts/evaluate")
            history_response = self.client.get("/api/v1/alerts")

            self.assertEqual(evaluation_response.status_code, 200)
            self.assertEqual(history_response.status_code, 200)

            payload = history_response.json()
            self.assertEqual(
                set(payload.keys()),
                {"generated_at", "alerts"},
                msg="Alert history response keys drift from docs/api/openapi.yml",
            )

            if payload["alerts"]:
                first = payload["alerts"][0]
                self.assertEqual(
                    set(first.keys()),
                    {
                        "id",
                        "created_at",
                        "market_id",
                        "question",
                        "market_probability",
                        "model_probability",
                        "edge",
                        "signal",
                        "status",
                    },
                    msg="Alert record fields drift from docs/api/openapi.yml",
                )
                self.assertIsInstance(
                    first["id"],
                    str,
                    msg="Alert record id type drifts from docs/api/openapi.yml",
                )
                self.assertIn(
                    first["status"],
                    {"open", "dismissed", "resolved"},
                    msg="Alert status drift from docs/api/openapi.yml",
                )
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

    def test_alert_evaluation_matches_documented_schema(self) -> None:
        original_database_url = os.environ.get("DATABASE_URL")
        database_path = (
            REPO_ROOT / "tests" / "acceptance" / f"acceptance-alert-eval-{uuid4().hex}.db"
        )
        try:
            os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

            response = self.client.post("/api/v1/alerts/evaluate")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(
                set(payload.keys()),
                {"evaluated_at", "created_count", "alerts"},
                msg="Alert evaluation response keys drift from docs/api/openapi.yml",
            )
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


if __name__ == "__main__":
    unittest.main()
