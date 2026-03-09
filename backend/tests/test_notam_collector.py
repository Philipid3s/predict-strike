import unittest

from src.collectors.notam import (
    BOOTSTRAP_NOTAM_RESPONSE,
    NotamCollector,
    compute_notam_spike,
    parse_notices,
)


class NotamCollectorTests(unittest.TestCase):
    def test_parse_notices_extracts_bootstrap_payload(self) -> None:
        notices = parse_notices(BOOTSTRAP_NOTAM_RESPONSE)

        self.assertEqual(len(notices), 3)
        self.assertEqual(notices[0].notice_id, "NOTAM-A1")

    def test_fallback_payload_is_used_when_loader_fails(self) -> None:
        collector = NotamCollector(
            payload_loader=lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        observation = collector.fetch_observation()

        self.assertEqual(observation.status, "degraded")
        self.assertEqual(len(observation.notices), 3)
        self.assertGreater(observation.notam_spike, 0.0)

    def test_notam_spike_highlights_restricted_activity(self) -> None:
        notices = parse_notices(BOOTSTRAP_NOTAM_RESPONSE)

        spike = compute_notam_spike(notices)

        self.assertGreaterEqual(spike, 0.6)


if __name__ == "__main__":
    unittest.main()
