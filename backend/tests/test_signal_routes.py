from pathlib import Path
import os
import sqlite3
import sys
import unittest

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.main import app  # noqa: E402


class SignalRouteTests(unittest.TestCase):
    def test_refresh_endpoint_returns_latest_snapshot_shape_and_persists(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "route-refresh.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)

            latest_response = client.get("/api/v1/signals/latest")
            refresh_response = client.post("/api/v1/signals/refresh")

            self.assertEqual(latest_response.status_code, 200)
            self.assertEqual(refresh_response.status_code, 200)

            refreshed_payload = refresh_response.json()
            self.assertIn("generated_at", refreshed_payload)
            self.assertIn("features", refreshed_payload)
            self.assertIn("sources", refreshed_payload)
            self.assertTrue(all("mode" in source for source in refreshed_payload["sources"]))

            with sqlite3.connect(str(database_path)) as connection:
                observation_count = connection.execute(
                    "SELECT COUNT(*) FROM source_observations"
                ).fetchone()[0]
                snapshot_count = connection.execute(
                    "SELECT COUNT(*) FROM signal_snapshots"
                ).fetchone()[0]
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(observation_count, 6)
        self.assertEqual(snapshot_count, 2)


if __name__ == "__main__":
    unittest.main()
