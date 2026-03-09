from pathlib import Path
import os
import sqlite3
import unittest

from src.services.market_pipeline import get_market_opportunities


class MarketPipelineTests(unittest.TestCase):
    def test_market_opportunities_are_collected_and_persisted(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "markets.db"
        if database_path.exists():
            database_path.unlink()

        database_url = f"sqlite:///{database_path.as_posix()}"
        previous_database_url = os.environ.get("DATABASE_URL")
        try:
            os.environ["DATABASE_URL"] = database_url
            response = get_market_opportunities()

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

        self.assertGreaterEqual(len(response.opportunities), 1)
        self.assertGreaterEqual(observation_count, 4)
        self.assertEqual(polymarket_count, 1)
        self.assertEqual(response.source.name, "Polymarket")
        self.assertIn(response.source.status, {"active", "degraded"})
        self.assertIn(response.source.mode, {"live", "fallback"})
        self.assertIn(response.upstream, {"gamma", "pizzint", "bootstrap"})


if __name__ == "__main__":
    unittest.main()
