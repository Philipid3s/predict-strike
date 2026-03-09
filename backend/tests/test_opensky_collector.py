import unittest

from src.collectors.opensky import (
    BOOTSTRAP_OPENSKY_RESPONSE,
    OpenSkyCollector,
    compute_flight_anomaly,
    parse_states,
)


class OpenSkyCollectorTests(unittest.TestCase):
    def test_parse_states_extracts_bootstrap_payload(self) -> None:
        states = parse_states(BOOTSTRAP_OPENSKY_RESPONSE)

        self.assertEqual(len(states), 4)
        self.assertEqual(states[0].callsign, "RCH123")

    def test_fallback_payload_is_used_when_loader_fails(self) -> None:
        collector = OpenSkyCollector(payload_loader=lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        observation = collector.fetch_observation()

        self.assertEqual(observation.status, "degraded")
        self.assertEqual(len(observation.states), 4)
        self.assertGreater(observation.flight_anomaly, 0.0)

    def test_flight_anomaly_highlights_military_like_activity(self) -> None:
        states = parse_states(BOOTSTRAP_OPENSKY_RESPONSE)

        anomaly = compute_flight_anomaly(states)

        self.assertGreaterEqual(anomaly, 0.5)


if __name__ == "__main__":
    unittest.main()
