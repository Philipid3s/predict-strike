import unittest

from src.config.opensky_registry import US_NATO_MILITARY_AIRFIELDS
from src.collectors.opensky import (
    BOOTSTRAP_OPENSKY_RESPONSE,
    OpenSkyCollector,
    OpenSkyState,
    assess_opensky_anomalies,
    compute_flight_anomaly,
    dominant_suspicious_region_name,
    departure_airfield_name,
    military_cluster_size,
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

        self.assertGreaterEqual(anomaly, 0.15)

    def test_bootstrap_payload_forms_a_military_callsign_cluster(self) -> None:
        states = parse_states(BOOTSTRAP_OPENSKY_RESPONSE)

        self.assertEqual(military_cluster_size(states), 2)

    def test_dominant_region_and_airfield_helpers_are_targeted(self) -> None:
        states = [
            OpenSkyState(
                icao24="sector01",
                callsign="RCH111",
                origin_country="United States",
                longitude=32.2,
                latitude=42.3,
                baro_altitude=9400.0,
                velocity=210.0,
                geo_altitude=9500.0,
            ),
            OpenSkyState(
                icao24="sector02",
                callsign="NATO22",
                origin_country="Luxembourg",
                longitude=33.1,
                latitude=43.1,
                baro_altitude=9700.0,
                velocity=220.0,
                geo_altitude=9800.0,
            ),
            OpenSkyState(
                icao24="sector03",
                callsign="RRR333",
                origin_country="United Kingdom",
                longitude=34.4,
                latitude=44.2,
                baro_altitude=9900.0,
                velocity=225.0,
                geo_altitude=10050.0,
            ),
        ]

        self.assertEqual(dominant_suspicious_region_name(states), "42-48N / 30-36E sector")
        self.assertIsNone(departure_airfield_name(states[0]))

    def test_dominant_region_is_none_without_a_real_cluster(self) -> None:
        states = [
            OpenSkyState(
                icao24="solo01",
                callsign="RCH101",
                origin_country="United States",
                longitude=10.0,
                latitude=40.0,
                baro_altitude=9200.0,
                velocity=220.0,
                geo_altitude=9300.0,
            ),
            OpenSkyState(
                icao24="solo02",
                callsign="RRR202",
                origin_country="United Kingdom",
                longitude=-75.0,
                latitude=39.0,
                baro_altitude=9100.0,
                velocity=215.0,
                geo_altitude=9200.0,
            ),
        ]

        self.assertIsNone(dominant_suspicious_region_name(states))

    def test_no_flagged_flights_results_in_zero_anomaly_score(self) -> None:
        states = [
            OpenSkyState(
                icao24="civil01",
                callsign="DAL220",
                origin_country="United States",
                longitude=-77.04,
                latitude=38.91,
                baro_altitude=9200.0,
                velocity=190.0,
                geo_altitude=9350.0,
            ),
            OpenSkyState(
                icao24="civil02",
                callsign="AAL102",
                origin_country="United States",
                longitude=-84.1,
                latitude=39.85,
                baro_altitude=11000.0,
                velocity=250.0,
                geo_altitude=11250.0,
            ),
        ]

        self.assertEqual(compute_flight_anomaly(states), 0.0)

    def test_score_is_zero_when_no_flights_match_anomaly_rules(self) -> None:
        states = [
            OpenSkyState(
                icao24="civil01",
                callsign="AAL101",
                origin_country="United States",
                longitude=-73.78,
                latitude=40.64,
                baro_altitude=10300.0,
                velocity=240.0,
                geo_altitude=10400.0,
            ),
            OpenSkyState(
                icao24="civil02",
                callsign="DAL202",
                origin_country="United States",
                longitude=-0.45,
                latitude=51.47,
                baro_altitude=9800.0,
                velocity=230.0,
                geo_altitude=9900.0,
            ),
        ]

        self.assertEqual(assess_opensky_anomalies(states), [])
        self.assertEqual(compute_flight_anomaly(states), 0.0)

    def test_airfield_registry_is_expanded_for_us_and_nato_focus(self) -> None:
        self.assertGreaterEqual(len(US_NATO_MILITARY_AIRFIELDS), 20)
        self.assertTrue(any(airfield.name == "Ramstein AB" for airfield in US_NATO_MILITARY_AIRFIELDS))
        self.assertTrue(any(airfield.name == "RAF Lakenheath" for airfield in US_NATO_MILITARY_AIRFIELDS))
        self.assertTrue(
            any(airfield.name == "NATO Air Base Geilenkirchen" for airfield in US_NATO_MILITARY_AIRFIELDS)
        )

    def test_departure_airfield_helper_detects_expanded_registry_entries(self) -> None:
        state = OpenSkyState(
            icao24="test01",
            callsign="RCH777",
            origin_country="United States",
            longitude=0.58,
            latitude=52.41,
            baro_altitude=2500.0,
            velocity=145.0,
            geo_altitude=2600.0,
        )

        self.assertEqual(departure_airfield_name(state), "RAF Lakenheath")


if __name__ == "__main__":
    unittest.main()
