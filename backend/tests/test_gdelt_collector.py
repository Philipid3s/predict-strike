import unittest

from src.collectors.gdelt import (
    BOOTSTRAP_GDELT_RESPONSE,
    GdeltCollector,
    compute_news_volume,
    parse_articles,
)


class GdeltCollectorTests(unittest.TestCase):
    def test_parse_articles_extracts_bootstrap_payload(self) -> None:
        articles = parse_articles(BOOTSTRAP_GDELT_RESPONSE)

        self.assertEqual(len(articles), 4)
        self.assertEqual(articles[0].article_id, "GDELT-1")

    def test_fallback_payload_is_used_when_loader_fails(self) -> None:
        collector = GdeltCollector(
            payload_loader=lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        observation = collector.fetch_observation()

        self.assertEqual(observation.status, "degraded")
        self.assertEqual(len(observation.articles), 4)
        self.assertGreater(observation.news_volume, 0.0)

    def test_news_volume_highlights_conflict_coverage(self) -> None:
        articles = parse_articles(BOOTSTRAP_GDELT_RESPONSE)

        volume = compute_news_volume(articles)

        self.assertGreaterEqual(volume, 0.7)


if __name__ == "__main__":
    unittest.main()
