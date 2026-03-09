from pathlib import Path
import sqlite3
import unittest
import os
from unittest.mock import patch

from src.services.seed_data import (
    get_latest_pizza_index,
    get_latest_signals,
    get_pizza_index_target_activity,
    list_pizza_index_targets,
    refresh_latest_signals,
)


class SeedDataTests(unittest.TestCase):
    def test_latest_signals_are_persisted_when_storage_is_empty(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "persisted.db"
        if database_path.exists():
            database_path.unlink()

        database_url = f"sqlite:///{database_path.as_posix()}"
        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = database_url
        try:
            first_snapshot = get_latest_signals()
            second_snapshot = get_latest_signals()
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url

        self.assertEqual(first_snapshot.generated_at, second_snapshot.generated_at)
        self.assertGreater(first_snapshot.features.notam_spike, 0.0)
        self.assertGreater(first_snapshot.features.news_volume, 0.0)

    def test_refresh_latest_signals_persists_a_new_snapshot(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "refreshed.db"
        if database_path.exists():
            database_path.unlink()

        database_url = f"sqlite:///{database_path.as_posix()}"
        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = database_url
        try:
            first_snapshot = get_latest_signals()
            refreshed_snapshot = refresh_latest_signals()

            with sqlite3.connect(str(database_path)) as connection:
                observation_count = connection.execute(
                    "SELECT COUNT(*) FROM source_observations"
                ).fetchone()[0]
                snapshot_count = connection.execute(
                    "SELECT COUNT(*) FROM signal_snapshots"
                ).fetchone()[0]
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url

        self.assertNotEqual(first_snapshot.generated_at, refreshed_snapshot.generated_at)
        self.assertEqual(observation_count, 6)
        self.assertEqual(snapshot_count, 2)

    def test_latest_signals_sources_match_documented_contract(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "contract.db"
        if database_path.exists():
            database_path.unlink()

        database_url = f"sqlite:///{database_path.as_posix()}"
        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = database_url
        try:
            snapshot = get_latest_signals()
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url

        self.assertGreaterEqual(len(snapshot.sources), 6)
        self.assertIn("NOTAM Feed", {source.name for source in snapshot.sources})
        self.assertIn("GDELT", {source.name for source in snapshot.sources})
        self.assertIn("Satellite Monitoring", {source.name for source in snapshot.sources})
        self.assertIn("Pizza Index Activity", {source.name for source in snapshot.sources})
        self.assertNotIn("Polymarket", {source.name for source in snapshot.sources})
        for source in snapshot.sources:
            self.assertFalse(hasattr(source, "category"))
            self.assertIn(source.status, {"planned", "active", "degraded"})
            self.assertIn(source.mode, {"live", "fallback", "static_baseline"})

    def test_pizza_index_seed_data_exposes_registry_and_snapshot(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "pizza-index-seed.db"
        if database_path.exists():
            database_path.unlink()

        database_url = f"sqlite:///{database_path.as_posix()}"
        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = database_url
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
                            "current_popularity": 74,
                            "percentage_of_usual": 161.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        },
                        {
                            "place_id": "ChIJo03BaX-3t4kRbyhPM0rTuqM",
                            "name": "Papa Johns Pizza",
                            "address": "https://www.google.com/maps/place/Papa+Johns+Pizza",
                            "current_popularity": 72,
                            "percentage_of_usual": 156.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        },
                        {
                            "place_id": "ChIJS1rpOC-3t4kRsLyM6aftM8k",
                            "name": "We, The Pizza",
                            "address": "https://www.google.com/maps/place/We,+The+Pizza",
                            "current_popularity": 70,
                            "percentage_of_usual": 152.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        },
                        {
                            "place_id": "ChIJcYireCe3t4kR4d9trEbGYjc",
                            "name": "Extreme Pizza",
                            "address": "https://www.google.com/maps/place/Extreme+Pizza",
                            "current_popularity": 68,
                            "percentage_of_usual": 148.0,
                            "is_closed_now": False,
                            "baseline_popular_times": {},
                        },
                    ],
                },
            ):
                targets = list_pizza_index_targets()
                snapshot = get_latest_pizza_index()
                activity = get_pizza_index_target_activity("dominos_pentagon_city")
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url

        self.assertGreaterEqual(len(targets.targets), 4)
        self.assertGreater(snapshot.pizza_index, 0.0)
        self.assertIsNotNone(activity)


if __name__ == "__main__":
    unittest.main()
