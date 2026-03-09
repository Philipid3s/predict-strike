import unittest

from src.collectors.polymarket import (
    BOOTSTRAP_POLYMARKET_RESPONSE,
    PolymarketCollector,
    DEFAULT_PIZZINT_POLYMARKET_BREAKING_URL,
    normalize_source_url,
    parse_markets,
)


class PolymarketCollectorTests(unittest.TestCase):
    def test_parse_markets_extracts_geopolitical_bootstrap_payload(self) -> None:
        markets = parse_markets(BOOTSTRAP_POLYMARKET_RESPONSE)

        self.assertEqual(len(markets), 2)
        self.assertEqual(markets[0].market_id, "poly-market-1")

    def test_fallback_payload_is_used_when_loader_fails(self) -> None:
        collector = PolymarketCollector(
            payload_loader=lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        observation = collector.fetch_observation()

        self.assertEqual(observation.status, "degraded")
        self.assertEqual(observation.upstream, "bootstrap")
        self.assertGreaterEqual(len(observation.markets), 1)
        self.assertGreater(observation.markets[0].market_probability, 0.0)

    def test_pizzint_fallback_payload_is_used_before_bootstrap(self) -> None:
        collector = PolymarketCollector(
            payload_loader=lambda: (_ for _ in ()).throw(RuntimeError("gamma blocked")),
            pizzint_payload_loader=lambda: {
                "markets": [
                    {
                        "market_id": "1465973",
                        "title": "Will US or Israel strike Iran on March 8, 2026?",
                        "latest_price": 0.997,
                        "volume24h": 95543.709811,
                    }
                ]
            },
        )

        observation = collector.fetch_observation()

        self.assertEqual(observation.status, "degraded")
        self.assertEqual(observation.upstream, "pizzint")
        self.assertEqual(len(observation.markets), 1)
        self.assertEqual(observation.markets[0].market_id, "1465973")
        self.assertEqual(
            observation.markets[0].question,
            "Will US or Israel strike Iran on March 8, 2026?",
        )
        self.assertEqual(observation.markets[0].market_probability, 0.997)

    def test_gamma_payload_marks_gamma_upstream(self) -> None:
        collector = PolymarketCollector(
            payload_loader=lambda: [
                {
                    "id": "evt-1",
                    "title": "Middle East Escalation",
                    "markets": [
                        {
                            "id": "mkt-1",
                            "question": "Will a direct strike occur before April?",
                            "outcomes": ["Yes", "No"],
                            "outcomePrices": ["0.27", "0.73"],
                            "volume24hr": 12345,
                        }
                    ],
                }
            ]
        )

        observation = collector.fetch_observation()

        self.assertEqual(observation.status, "active")
        self.assertEqual(observation.upstream, "gamma")

    def test_parse_markets_handles_top_level_event_list_payload(self) -> None:
        payload = [
            {
                "id": "evt-1",
                "title": "Middle East Escalation",
                "markets": [
                    {
                        "id": "mkt-1",
                        "question": "Will a direct strike occur before April?",
                        "outcomes": ["Yes", "No"],
                        "outcomePrices": ["0.27", "0.73"],
                        "volume24hr": 12345,
                    }
                ],
            }
        ]

        markets = parse_markets(payload)

        self.assertEqual(len(markets), 1)
        self.assertEqual(markets[0].market_id, "mkt-1")
        self.assertEqual(markets[0].market_probability, 0.27)

    def test_parse_markets_handles_pizzint_breaking_payload(self) -> None:
        payload = {
            "markets": [
                {
                    "market_id": "1465973",
                    "title": "Will US or Israel strike Iran on March 8, 2026?",
                    "latest_price": 0.997,
                    "volume24h": 95543.709811,
                }
            ]
        }

        markets = parse_markets(payload)

        self.assertEqual(len(markets), 1)
        self.assertEqual(markets[0].market_id, "1465973")
        self.assertEqual(
            markets[0].question, "Will US or Israel strike Iran on March 8, 2026?"
        )
        self.assertEqual(markets[0].market_probability, 0.997)
        self.assertEqual(markets[0].volume, 95543.7098)

    def test_base_gamma_url_is_normalized_to_events_endpoint(self) -> None:
        normalized = normalize_source_url("https://gamma-api.polymarket.com/")

        self.assertEqual(
            normalized,
            "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=50",
        )

    def test_default_pizzint_breaking_url_is_configured(self) -> None:
        self.assertEqual(
            DEFAULT_PIZZINT_POLYMARKET_BREAKING_URL,
            "https://www.pizzint.watch/api/markets/breaking?window=6h&final_limit=20&format=ticker",
        )


if __name__ == "__main__":
    unittest.main()
