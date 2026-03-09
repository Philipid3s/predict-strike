from datetime import date, datetime
from pathlib import Path
import unittest

from src.models.schemas import FeatureSet, LatestSignalsResponse, SignalSource
from src.storage.signal_store import SignalStore, database_path_from_url


class SignalStoreTests(unittest.TestCase):
    def test_database_path_resolves_relative_sqlite_url_within_backend(self) -> None:
        path = database_path_from_url("sqlite:///./predict-strike.db")

        self.assertTrue(str(path).endswith("backend\\predict-strike.db"))

    def test_save_and_read_latest_signal_snapshot(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "signals.db"
        if database_path.exists():
            database_path.unlink()

        database_url = f"sqlite:///{database_path.as_posix()}"
        store = SignalStore(database_url)
        snapshot = LatestSignalsResponse(
            generated_at=datetime.fromisoformat("2026-03-07T00:00:00+00:00"),
            region_focus="global-watchlist",
            features=FeatureSet(
                flight_anomaly=0.55,
                notam_spike=0.42,
                satellite_buildup=0.37,
                news_volume=0.61,
                osint_activity=0.49,
                pizza_index=0.18,
            ),
            sources=[
                SignalSource(
                    name="OpenSky Network",
                    status="active",
                    mode="live",
                    last_checked_at=datetime.fromisoformat("2026-03-07T00:00:00+00:00"),
                )
            ],
        )

        store.save_source_observation(
            source_name="OpenSky Network",
            collected_at=snapshot.generated_at,
            status="active",
            payload={"states": []},
        )
        store.save_signal_snapshot(snapshot)
        loaded = store.get_latest_signal_snapshot()

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.features.flight_anomaly, 0.55)
        self.assertEqual(loaded.sources[0].status, "active")
        self.assertEqual(loaded.sources[0].mode, "live")

    def test_legacy_snapshot_without_mode_is_coerced_on_read(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "legacy-signals.db"
        if database_path.exists():
            database_path.unlink()

        database_url = f"sqlite:///{database_path.as_posix()}"
        store = SignalStore(database_url)
        with store._connect() as connection:
            connection.execute(
                """
                INSERT INTO signal_snapshots (
                    generated_at,
                    region_focus,
                    features_json,
                    sources_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    "2026-03-07T00:00:00+00:00",
                    "global-watchlist",
                    '{"flight_anomaly": 0.55, "notam_spike": 0.42, "satellite_buildup": 0.37, "news_volume": 0.61, "osint_activity": 0.49, "pizza_index": 0.18}',
                    '[{"name": "OpenSky Network", "status": "active", "last_checked_at": "2026-03-07T00:00:00+00:00"}]',
                ),
            )

        loaded = store.get_latest_signal_snapshot()

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.sources[0].mode, "live")

    def test_provider_daily_usage_persists_across_store_instances(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "provider-usage.db"
        if database_path.exists():
            database_path.unlink()

        database_url = f"sqlite:///{database_path.as_posix()}"
        first_store = SignalStore(database_url)
        allowed, count = first_store.try_consume_provider_daily_quota(
            provider_name="serpapi",
            usage_date=date.fromisoformat("2026-03-07"),
            daily_limit=4,
        )

        second_store = SignalStore(database_url)
        persisted_count = second_store.get_provider_daily_usage(
            "serpapi",
            date.fromisoformat("2026-03-07"),
        )

        self.assertTrue(allowed)
        self.assertEqual(count, 1)
        self.assertEqual(persisted_count, 1)

    def test_pizza_index_provider_payload_is_persisted_and_readable(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "pizza-provider-payloads.db"
        if database_path.exists():
            database_path.unlink()

        database_url = f"sqlite:///{database_path.as_posix()}"
        store = SignalStore(database_url)
        collected_at = datetime.fromisoformat("2026-03-07T00:00:00+00:00")

        store.save_pizza_index_provider_payload(
            target_id="dominos_pentagon_city",
            provider="pizzint",
            provider_mode="primary",
            collected_at=collected_at,
            payload={"current_busyness_percent": 77, "capture_status": "pizzint_dashboard_ok"},
        )
        loaded = store.get_latest_pizza_index_provider_payload(
            target_id="dominos_pentagon_city",
            provider="pizzint",
        )

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["current_busyness_percent"], 77)
        self.assertEqual(loaded["capture_status"], "pizzint_dashboard_ok")


if __name__ == "__main__":
    unittest.main()
