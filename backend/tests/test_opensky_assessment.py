from pathlib import Path
import json
import sys
import unittest
from urllib.error import HTTPError, URLError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.collectors.opensky import OpenSkyAnomalyAssessment, OpenSkyState  # noqa: E402
from src.services.opensky_assessment import (  # noqa: E402
    OpenSkyAssessmentConfig,
    OpenSkyStrikeAssessmentService,
    build_assessment_prompt,
    build_condensed_anomaly_list,
)


class OpenSkyAssessmentServiceTests(unittest.TestCase):
    def test_build_condensed_anomaly_list_keeps_only_requested_fields(self) -> None:
        assessment = OpenSkyAnomalyAssessment(
            state=OpenSkyState(
                icao24="abc123",
                callsign="RCH123",
                origin_country="United States",
                longitude=32.85,
                latitude=44.12,
                baro_altitude=9750.0,
                velocity=215.0,
                geo_altitude=10100.0,
            ),
            reasons=("military_like_callsign",),
        )

        condensed = build_condensed_anomaly_list([assessment])

        self.assertEqual(
            condensed,
            [
                {
                    "callsign": "RCH123",
                    "icao24": "abc123",
                    "position": {"latitude": 44.12, "longitude": 32.85},
                }
            ],
        )

    def test_prompt_contains_only_condensed_flight_list(self) -> None:
        assessment = OpenSkyAnomalyAssessment(
            state=OpenSkyState(
                icao24="def456",
                callsign="NATO45",
                origin_country="Luxembourg",
                longitude=43.8,
                latitude=33.1,
                baro_altitude=10450.0,
                velocity=236.0,
                geo_altitude=10620.0,
            ),
            reasons=("military_like_callsign", "military_callsign_cluster"),
        )

        prompt = build_assessment_prompt([assessment])

        self.assertIn('"callsign": "NATO45"', prompt)
        self.assertIn('"icao24": "def456"', prompt)
        self.assertIn('"latitude": 33.1', prompt)
        self.assertIn(
            "Role: You are a Military Intelligence Analyst specializing in Aerial OSINT.",
            prompt,
        )
        self.assertIn('Look for the "Strike Stack."', prompt)
        self.assertIn("Movement Trend", prompt)
        self.assertIn("Anomaly Note", prompt)
        self.assertIn('  "probability_percent": 0,', prompt)
        self.assertNotIn("origin_country", prompt)
        self.assertNotIn("reasons", prompt)

    def test_service_returns_disabled_when_configuration_missing(self) -> None:
        assessment = OpenSkyAnomalyAssessment(
            state=OpenSkyState(
                icao24="ghi789",
                callsign="ASCOT1",
                origin_country="United Kingdom",
                longitude=25.0,
                latitude=37.0,
                baro_altitude=9000.0,
                velocity=210.0,
                geo_altitude=9300.0,
            ),
            reasons=("tanker_transport_pattern",),
        )
        service = OpenSkyStrikeAssessmentService(
            OpenSkyAssessmentConfig(api_url=None, api_key=None, model=None)
        )

        result = service.assess_anomalies([assessment])

        self.assertEqual(result.status, "disabled")
        self.assertIsNone(result.probability_percent)
        self.assertEqual(result.countries, [])

    def test_service_parses_ai_response(self) -> None:
        assessment = OpenSkyAnomalyAssessment(
            state=OpenSkyState(
                icao24="abc123",
                callsign="RCH123",
                origin_country="United States",
                longitude=32.85,
                latitude=44.12,
                baro_altitude=9750.0,
                velocity=215.0,
                geo_altitude=10100.0,
            ),
            reasons=("military_like_callsign",),
        )

        captured_request: dict[str, str] = {}

        def fake_sender(request, timeout_seconds):
            captured_request["body"] = request.data.decode("utf-8")
            captured_request["timeout_seconds"] = str(timeout_seconds)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "probability_percent": 72,
                                    "countries": ["Russia", "Ukraine"],
                                    "explanation": "Airlift and NATO-adjacent traffic are elevated.",
                                }
                            )
                        }
                    }
                ]
            }

        service = OpenSkyStrikeAssessmentService(
            OpenSkyAssessmentConfig(
                api_url="https://example.test/v1/chat/completions",
                api_key="test-key",
                model="gpt-test",
                timeout_seconds=7,
            ),
            request_sender=fake_sender,
        )

        result = service.assess_anomalies([assessment])
        request_body = json.loads(captured_request["body"])

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.probability_percent, 72)
        self.assertEqual(result.countries, ["Russia", "Ukraine"])
        self.assertIn("Airlift and NATO-adjacent traffic", result.explanation or "")
        self.assertEqual(request_body["model"], "gpt-test")
        self.assertEqual(captured_request["timeout_seconds"], "7")
        self.assertIn('"icao24": "abc123"', request_body["messages"][1]["content"])

    def test_service_reports_upstream_connectivity_error(self) -> None:
        assessment = OpenSkyAnomalyAssessment(
            state=OpenSkyState(
                icao24="abc123",
                callsign="RCH123",
                origin_country="United States",
                longitude=32.85,
                latitude=44.12,
                baro_altitude=9750.0,
                velocity=215.0,
                geo_altitude=10100.0,
            ),
            reasons=("military_like_callsign",),
        )

        def failing_sender(request, timeout_seconds):
            raise URLError("temporary DNS failure")

        service = OpenSkyStrikeAssessmentService(
            OpenSkyAssessmentConfig(
                api_url="https://example.test/v1/chat/completions",
                api_key="test-key",
                model="gpt-test",
            ),
            request_sender=failing_sender,
        )

        result = service.assess_anomalies([assessment])

        self.assertEqual(result.status, "error")
        self.assertIsNone(result.probability_percent)
        self.assertEqual(result.countries, [])
        self.assertEqual(
            result.explanation,
            "AI request failed to reach the upstream model provider.",
        )

    def test_service_reports_http_error_from_upstream_provider(self) -> None:
        assessment = OpenSkyAnomalyAssessment(
            state=OpenSkyState(
                icao24="abc123",
                callsign="RCH123",
                origin_country="United States",
                longitude=32.85,
                latitude=44.12,
                baro_altitude=9750.0,
                velocity=215.0,
                geo_altitude=10100.0,
            ),
            reasons=("military_like_callsign",),
        )

        def failing_sender(request, timeout_seconds):
            raise HTTPError(
                url="https://example.test/v1/chat/completions",
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=None,
            )

        service = OpenSkyStrikeAssessmentService(
            OpenSkyAssessmentConfig(
                api_url="https://example.test/v1/chat/completions",
                api_key="test-key",
                model="gpt-test",
            ),
            request_sender=failing_sender,
        )

        result = service.assess_anomalies([assessment])

        self.assertEqual(result.status, "error")
        self.assertEqual(
            result.explanation,
            "AI request failed with HTTP 400 from the upstream model provider.",
        )

    def test_service_reports_json_parse_error_when_model_returns_non_json(self) -> None:
        assessment = OpenSkyAnomalyAssessment(
            state=OpenSkyState(
                icao24="abc123",
                callsign="RCH123",
                origin_country="United States",
                longitude=32.85,
                latitude=44.12,
                baro_altitude=9750.0,
                velocity=215.0,
                geo_altitude=10100.0,
            ),
            reasons=("military_like_callsign",),
        )

        def fake_sender(request, timeout_seconds):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Probability 70%. Countries: Russia, Ukraine.",
                        }
                    }
                ]
            }

        service = OpenSkyStrikeAssessmentService(
            OpenSkyAssessmentConfig(
                api_url="https://example.test/v1/chat/completions",
                api_key="test-key",
                model="gpt-test",
            ),
            request_sender=fake_sender,
        )

        result = service.assess_anomalies([assessment])

        self.assertEqual(result.status, "error")
        self.assertEqual(
            result.explanation,
            "AI response could not be parsed as the required JSON object.",
        )

    def test_service_reports_schema_validation_error_when_fields_are_missing(self) -> None:
        assessment = OpenSkyAnomalyAssessment(
            state=OpenSkyState(
                icao24="abc123",
                callsign="RCH123",
                origin_country="United States",
                longitude=32.85,
                latitude=44.12,
                baro_altitude=9750.0,
                velocity=215.0,
                geo_altitude=10100.0,
            ),
            reasons=("military_like_callsign",),
        )

        def fake_sender(request, timeout_seconds):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "probability_percent": "72",
                                    "countries": ["Russia"],
                                    "explanation": "Traffic concentration detected.",
                                }
                            )
                        }
                    }
                ]
            }

        service = OpenSkyStrikeAssessmentService(
            OpenSkyAssessmentConfig(
                api_url="https://example.test/v1/chat/completions",
                api_key="test-key",
                model="gpt-test",
            ),
            request_sender=fake_sender,
        )

        result = service.assess_anomalies([assessment])

        self.assertEqual(result.status, "error")
        self.assertEqual(
            result.explanation,
            "AI response JSON did not match the required fields: probability_percent, countries, explanation.",
        )


if __name__ == "__main__":
    unittest.main()
