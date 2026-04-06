from pathlib import Path
import json
import sys
import unittest
from urllib.error import URLError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.collectors.notam import NotamNotice  # noqa: E402
from src.services.notam_assessment import (  # noqa: E402
    NotamAssessmentConfig,
    NotamStrikeAssessmentService,
    build_assessment_prompt,
)


class NotamAssessmentServiceTests(unittest.TestCase):
    def _build_notices(self) -> list[NotamNotice]:
        return [
            NotamNotice(
                notice_id="notam-1",
                location="KADW",
                classification="MILITARY",
                text="AIRSPACE RESTRICTION FOR MILITARY EXERCISE",
                effective_start="202604051021",
                effective_end="202604051621",
            ),
            NotamNotice(
                notice_id="notam-2",
                location="KPAM",
                classification="RESTRICTED AIRSPACE",
                text="MISSILE ACTIVITY. TFR ACTIVE.",
                effective_start="202604051121",
                effective_end="202604051421",
            ),
        ]

    def test_build_assessment_prompt_condenses_notams_for_ai_input(self) -> None:
        prompt = build_assessment_prompt(self._build_notices())

        self.assertIn("raw_notice_count", prompt)
        self.assertIn("representative_notices", prompt)
        self.assertIn("KADW", prompt)
        self.assertIn("probability_percent", prompt)
        self.assertIn("target_country", prompt)

    def test_service_returns_ready_ai_assessment(self) -> None:
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
                                    "probability_percent": 77,
                                    "target_region": "North America",
                                    "target_country": "United States",
                                    "summary": "Clustered military NOTAMs indicate elevated strike risk.",
                                }
                            )
                        }
                    }
                ]
            }

        service = NotamStrikeAssessmentService(
            NotamAssessmentConfig(
                api_url="https://example.test/v1/chat/completions",
                api_key="test-key",
                model="gpt-test",
                timeout_seconds=9,
            ),
            request_sender=fake_sender,
        )

        result = service.assess_notices(self._build_notices())
        request_body = json.loads(captured_request["body"])

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.probability_percent, 77)
        self.assertEqual(result.target_country, "United States")
        self.assertEqual(result.target_region, "North America")
        self.assertEqual(result.assessed_notice_count, 2)
        self.assertGreater(result.freshness_score, 0.0)
        self.assertEqual(captured_request["timeout_seconds"], "9")
        self.assertEqual(request_body["model"], "gpt-test")
        self.assertIn("KADW", request_body["messages"][1]["content"])

    def test_service_returns_disabled_when_configuration_missing(self) -> None:
        service = NotamStrikeAssessmentService(
            NotamAssessmentConfig(api_url=None, api_key=None, model=None)
        )

        result = service.assess_notices(self._build_notices())

        self.assertEqual(result.status, "disabled")
        self.assertIsNone(result.probability_percent)
        self.assertEqual(result.assessed_notice_count, 2)
        self.assertGreater(result.freshness_score, 0.0)

    def test_service_reports_upstream_connectivity_error(self) -> None:
        def fake_sender(request, timeout_seconds):
            raise URLError("temporary DNS failure")

        service = NotamStrikeAssessmentService(
            NotamAssessmentConfig(
                api_url="https://example.test/v1/chat/completions",
                api_key="test-key",
                model="gpt-test",
            ),
            request_sender=fake_sender,
        )

        result = service.assess_notices(self._build_notices())

        self.assertEqual(result.status, "error")
        self.assertIsNone(result.probability_percent)
        self.assertEqual(result.assessed_notice_count, 2)
        self.assertEqual(result.summary, "AI request failed to reach the upstream model provider.")


if __name__ == "__main__":
    unittest.main()
