import unittest

from src.services.risk_engine import (
    ALERT_THRESHOLD,
    DEFAULT_WEIGHTS,
    WATCH_THRESHOLD,
    normalize_weights,
    score_features,
)


class RiskEngineTests(unittest.TestCase):
    def test_low_scoring_returns_monitor_classification(self) -> None:
        result = score_features(
            {
                "flight_anomaly": 0.1,
                "notam_spike": 0.05,
                "satellite_buildup": 0.0,
                "news_volume": 0.1,
                "osint_activity": 0.05,
                "pizza_index": 0.0,
            }
        )

        self.assertLess(result.score, WATCH_THRESHOLD)
        self.assertEqual(result.classification, "monitor")

    def test_default_scoring_returns_watch_classification(self) -> None:
        result = score_features(
            {
                "flight_anomaly": 0.8,
                "notam_spike": 0.5,
                "satellite_buildup": 0.3,
                "news_volume": 0.7,
                "osint_activity": 0.4,
                "pizza_index": 0.2,
            }
        )

        expected_score = round(
            0.8 * DEFAULT_WEIGHTS["flight_anomaly"]
            + 0.5 * DEFAULT_WEIGHTS["notam_spike"]
            + 0.3 * DEFAULT_WEIGHTS["satellite_buildup"]
            + 0.7 * DEFAULT_WEIGHTS["news_volume"]
            + 0.4 * DEFAULT_WEIGHTS["osint_activity"]
            + 0.2 * DEFAULT_WEIGHTS["pizza_index"],
            4,
        )

        self.assertEqual(result.score, expected_score)
        self.assertGreaterEqual(result.score, WATCH_THRESHOLD)
        self.assertLess(result.score, ALERT_THRESHOLD)
        self.assertEqual(result.classification, "watch")

    def test_default_weights_only_allocate_score_to_active_signals(self) -> None:
        weights = normalize_weights()

        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertEqual(weights["satellite_buildup"], 0.0)
        self.assertEqual(weights["osint_activity"], 0.0)
        self.assertEqual(weights["flight_anomaly"], DEFAULT_WEIGHTS["flight_anomaly"])
        self.assertEqual(weights["notam_spike"], DEFAULT_WEIGHTS["notam_spike"])
        self.assertEqual(weights["news_volume"], DEFAULT_WEIGHTS["news_volume"])
        self.assertEqual(weights["pizza_index"], DEFAULT_WEIGHTS["pizza_index"])

    def test_weight_overrides_are_normalized(self) -> None:
        weights = normalize_weights(
            {
                "flight_anomaly": 3.0,
                "notam_spike": 1.0,
                "satellite_buildup": 1.0,
                "news_volume": 1.0,
                "osint_activity": 1.0,
                "pizza_index": 1.0,
            }
        )

        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["flight_anomaly"], 0.375)
        self.assertGreater(weights["flight_anomaly"], weights["notam_spike"])


if __name__ == "__main__":
    unittest.main()
