from pathlib import Path
import os
import sqlite3
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.main import app  # noqa: E402
from src.models.schemas import GdeltSignalAssessment, OpenSkyStrikeAssessment  # noqa: E402


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

    def test_refresh_source_endpoint_updates_single_source_and_persists(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "route-refresh-source.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)

            latest_response = client.get("/api/v1/signals/latest")
            refresh_response = client.post(
                "/api/v1/signals/refresh-source",
                json={"source_name": "OpenSky Network"},
            )

            self.assertEqual(latest_response.status_code, 200)
            self.assertEqual(refresh_response.status_code, 200)

            refreshed_payload = refresh_response.json()
            self.assertEqual(refreshed_payload["source"]["name"], "OpenSky Network")
            self.assertIn("snapshot", refreshed_payload)
            self.assertIn("features", refreshed_payload["snapshot"])
            self.assertTrue(
                any(
                    source["name"] == "OpenSky Network"
                    for source in refreshed_payload["snapshot"]["sources"]
                )
            )

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

        self.assertEqual(observation_count, 4)
        self.assertEqual(snapshot_count, 2)

    def test_refresh_source_endpoint_does_not_change_opensky_signal_feature(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "route-refresh-source-opensky-feature.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)

            latest_response = client.get("/api/v1/signals/latest")
            latest_payload = latest_response.json()
            refresh_response = client.post(
                "/api/v1/signals/refresh-source",
                json={"source_name": "OpenSky Network"},
            )
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(latest_response.status_code, 200)
        self.assertEqual(refresh_response.status_code, 200)
        self.assertEqual(
            refresh_response.json()["snapshot"]["features"]["flight_anomaly"],
            latest_payload["features"]["flight_anomaly"],
        )

    def test_refresh_source_endpoint_rejects_static_baseline_source(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/api/v1/signals/refresh-source",
            json={"source_name": "Pizza Index Activity"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support individual refresh", response.json()["detail"])

    def test_opensky_anomalies_endpoint_returns_suspicious_flights_without_triggering_ai(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "opensky-anomalies.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)
            with patch(
                "src.services.signal_pipeline.OpenSkyStrikeAssessmentService.assess_anomalies",
                side_effect=AssertionError("anomalies endpoint must not call AI"),
            ):
                response = client.get("/api/v1/signals/sources/opensky-network/anomalies")
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("anomalies", payload)
        self.assertGreater(len(payload["anomalies"]), 0)
        self.assertIn("reasons", payload["anomalies"][0])
        self.assertIn("assessment", payload)
        self.assertEqual(payload["assessment"]["status"], "disabled")
        self.assertIsNone(payload["assessment"]["probability_percent"])
        self.assertEqual(payload["flight_anomaly"], 0.0)
        self.assertIn("Refresh Signal", payload["assessment"]["explanation"])
        flattened_reasons = {
            reason
            for anomaly in payload["anomalies"]
            for reason in anomaly["reasons"]
        }
        self.assertIn("military_like_callsign", flattened_reasons)
        self.assertIn("military_callsign_cluster", flattened_reasons)

    def test_gdelt_detail_endpoint_does_not_trigger_ai_assessment(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "gdelt-detail-no-ai.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)
            client.post(
                "/api/v1/signals/refresh-source",
                json={"source_name": "GDELT"},
            )
            with patch(
                "src.services.signal_pipeline.GdeltStrikeAssessmentService.assess_articles",
                side_effect=AssertionError("detail endpoint must not call Gemini"),
            ):
                response = client.get("/api/v1/signals/sources/gdelt/detail")
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assessment"]["status"], "disabled")
        self.assertIn("Refresh Signal", payload["assessment"]["summary"])

    def test_gdelt_detail_endpoint_returns_analyst_facing_breakdown(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "gdelt-detail.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)
            response = client.get("/api/v1/signals/sources/gdelt/detail")
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("article_count", payload)
        self.assertIn("top_themes", payload)
        self.assertIn("top_regions", payload)
        self.assertIn("top_sources", payload)
        self.assertIn("headlines", payload)
        self.assertIn("provenance", payload)
        self.assertIn("assessment", payload)
        self.assertIn("freshness_score", payload)
        self.assertIn("signal_article_count", payload)
        self.assertIn("collector_fallback_reason", payload["provenance"])
        self.assertGreater(payload["article_count"], 0)
        self.assertGreater(len(payload["headlines"]), 0)
        self.assertTrue(any(item["label"] == "Black Sea" for item in payload["top_regions"]))
        self.assertTrue(any(item["label"] == "Conflict & strikes" for item in payload["top_themes"]))
        self.assertEqual(payload["headlines"][0]["source_label"], "examplewire.test")
        self.assertIn("freshness_score", payload["headlines"][0])
        self.assertIn("is_us_nato_actor", payload["headlines"][0])
        self.assertIn("is_action_indicative", payload["headlines"][0])
        self.assertTrue(
            all(
                headline["published_at"] is None or "T" in headline["published_at"]
                for headline in payload["headlines"]
            )
        )

    def test_opensky_refresh_signal_updates_snapshot_feature_and_region(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "opensky-refresh-signal.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)
            client.get("/api/v1/signals/latest")
            with patch(
                "src.services.signal_pipeline.OpenSkyStrikeAssessmentService.assess_anomalies",
                return_value=OpenSkyStrikeAssessment(
                    status="ready",
                    prompt_version="opensky-strike-v2",
                    probability_percent=81,
                    countries=["Iran", "Israel"],
                    explanation="Military-adjacent traffic clusters suggest elevated operational preparation.",
                ),
            ):
                response = client.post("/api/v1/signals/sources/opensky-network/refresh-signal")
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assessment"]["status"], "ready")
        self.assertEqual(payload["snapshot"]["features"]["flight_anomaly"], 0.81)
        self.assertEqual(payload["snapshot"]["region_focus"], "Iran, Israel")

    def test_opensky_refresh_signal_sets_feature_to_zero_when_ai_assessment_is_not_ready(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "opensky-refresh-signal-error.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)
            client.get("/api/v1/signals/latest")
            with patch(
                "src.services.signal_pipeline.OpenSkyStrikeAssessmentService.assess_anomalies",
                return_value=OpenSkyStrikeAssessment(
                    status="error",
                    prompt_version="opensky-strike-v2",
                    probability_percent=None,
                    countries=[],
                    explanation="AI response could not be parsed as the required JSON object.",
                ),
            ):
                response = client.post("/api/v1/signals/sources/opensky-network/refresh-signal")
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assessment"]["status"], "error")
        self.assertEqual(payload["snapshot"]["features"]["flight_anomaly"], 0.0)

    def test_refresh_source_endpoint_does_not_change_gdelt_signal_feature(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "route-refresh-source-gdelt-feature.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)

            latest_response = client.get("/api/v1/signals/latest")
            latest_payload = latest_response.json()
            refresh_response = client.post(
                "/api/v1/signals/refresh-source",
                json={"source_name": "GDELT"},
            )
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(latest_response.status_code, 200)
        self.assertEqual(refresh_response.status_code, 200)
        self.assertEqual(
            refresh_response.json()["snapshot"]["features"]["news_volume"],
            latest_payload["features"]["news_volume"],
        )

    def test_gdelt_refresh_signal_updates_snapshot_feature_and_region(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "gdelt-refresh-signal.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)
            client.get("/api/v1/signals/latest")
            with patch(
                "src.services.signal_pipeline.GdeltStrikeAssessmentService.assess_articles",
                return_value=GdeltSignalAssessment(
                    status="ready",
                    prompt_version="gdelt-strike-v1",
                    probability_percent=72,
                    target_region="Eastern Mediterranean",
                    target_country="Syria",
                    summary="Recent reporting suggests elevated US/NATO strike preparation indicators.",
                    assessed_article_count=4,
                    freshness_score=0.88,
                ),
            ):
                response = client.post("/api/v1/signals/sources/gdelt/refresh-signal")
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assessment"]["status"], "ready")
        self.assertEqual(payload["snapshot"]["features"]["news_volume"], 0.72)
        self.assertEqual(payload["snapshot"]["region_focus"], "Syria")

    def test_gdelt_refresh_signal_sets_feature_to_zero_when_ai_assessment_is_not_ready(self) -> None:
        runtime_dir = Path(__file__).resolve().parent / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        database_path = runtime_dir / "gdelt-refresh-signal-error.db"
        if database_path.exists():
            database_path.unlink()

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        try:
            client = TestClient(app)
            client.get("/api/v1/signals/latest")
            with patch(
                "src.services.signal_pipeline.GdeltStrikeAssessmentService.assess_articles",
                return_value=GdeltSignalAssessment(
                    status="error",
                    prompt_version="gdelt-strike-v1",
                    probability_percent=None,
                    target_region=None,
                    target_country=None,
                    summary="AI response could not be parsed as the required JSON object.",
                    assessed_article_count=4,
                    freshness_score=0.51,
                ),
            ):
                response = client.post("/api/v1/signals/sources/gdelt/refresh-signal")
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assessment"]["status"], "error")
        self.assertEqual(payload["snapshot"]["features"]["news_volume"], 0.0)


if __name__ == "__main__":
    unittest.main()
