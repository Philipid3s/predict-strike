import unittest
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.collectors.gdelt import (
    BOOTSTRAP_GDELT_RESPONSE,
    GdeltCollector,
    article_source_label,
    compute_news_volume,
    extract_article_regions,
    extract_article_themes,
    is_gdelt_doc_payload,
    is_alert_article,
    parse_articles,
)
from src.services.gdelt_assessment import (
    build_signal_article_set,
    compute_article_freshness_score,
    filter_recent_articles,
    is_action_indicative_article,
    is_us_nato_action_article,
    is_us_nato_actor_article,
)


class GdeltCollectorTests(unittest.TestCase):
    def test_parse_articles_extracts_gdelt_doc_article_list_payload(self) -> None:
        payload = {
            "articles": [
                {
                    "url": "https://www.gdeltproject.org/example-article",
                    "title": "Conflict pressure builds around shipping corridor",
                    "seendate": "2026-03-07T08:20:00Z",
                    "domain": "gdeltproject.org",
                }
            ]
        }

        articles = parse_articles(payload)

        self.assertEqual(len(articles), 1)
        self.assertEqual(
            articles[0].article_id,
            "https://www.gdeltproject.org/example-article",
        )
        self.assertEqual(articles[0].source, "gdeltproject.org")
        self.assertEqual(articles[0].published_at, "2026-03-07T08:20:00Z")

    def test_parse_articles_normalizes_common_gdelt_timestamp_shapes(self) -> None:
        payload = {
            "articles": [
                {
                    "id": "compact-ts",
                    "title": "Mobilization watch",
                    "seendate": "20260307T082000Z",
                    "domain": "gdeltproject.org",
                },
                {
                    "id": "invalid-ts",
                    "title": "Market wrap",
                    "seendate": "not-a-timestamp",
                    "domain": "gdeltproject.org",
                },
            ]
        }

        articles = parse_articles(payload)

        self.assertEqual(articles[0].published_at, "2026-03-07T08:20:00Z")
        self.assertIsNone(articles[1].published_at)

    def test_parse_articles_extracts_bootstrap_payload(self) -> None:
        articles = parse_articles(BOOTSTRAP_GDELT_RESPONSE)

        self.assertEqual(len(articles), 4)
        self.assertEqual(articles[0].article_id, "GDELT-1")
        self.assertTrue(is_gdelt_doc_payload(BOOTSTRAP_GDELT_RESPONSE))

    def test_fallback_payload_is_used_when_loader_fails(self) -> None:
        collector = GdeltCollector(
            payload_loader=lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        observation = collector.fetch_observation()

        self.assertEqual(observation.status, "degraded")
        self.assertEqual(len(observation.articles), 4)
        self.assertGreater(observation.news_volume, 0.0)
        self.assertEqual(observation.fallback_reason, "RuntimeError: boom")

    def test_non_doc_payload_is_rejected_and_falls_back(self) -> None:
        collector = GdeltCollector(payload_loader=lambda: {"items": []})

        observation = collector.fetch_observation()

        self.assertEqual(observation.status, "degraded")
        self.assertEqual(len(observation.articles), 4)
        self.assertIn("ValueError", observation.fallback_reason)

    def test_malformed_article_rows_trigger_fallback_payload(self) -> None:
        collector = GdeltCollector(payload_loader=lambda: {"articles": [None, "bad-row", 7]})

        observation = collector.fetch_observation()

        self.assertEqual(observation.status, "degraded")
        self.assertEqual(len(observation.articles), 4)
        self.assertEqual(observation.raw_payload, BOOTSTRAP_GDELT_RESPONSE)
        self.assertIn("ValueError", observation.fallback_reason)

    def test_news_volume_highlights_conflict_coverage(self) -> None:
        articles = parse_articles(BOOTSTRAP_GDELT_RESPONSE)

        volume = compute_news_volume(articles)

        self.assertGreaterEqual(volume, 0.7)

    def test_article_helpers_extract_regions_themes_and_source_labels(self) -> None:
        articles = parse_articles(BOOTSTRAP_GDELT_RESPONSE)

        self.assertTrue(is_alert_article(articles[0]))
        self.assertIn("Black Sea", extract_article_regions(articles[0]))
        self.assertIn("Conflict & strikes", extract_article_themes(articles[0]))
        self.assertEqual(article_source_label(articles[0]), "examplewire.test")

    def test_freshness_score_prefers_more_recent_articles(self) -> None:
        articles = parse_articles(BOOTSTRAP_GDELT_RESPONSE)

        freshest = compute_article_freshness_score(articles[-1])
        older = compute_article_freshness_score(articles[0])

        self.assertGreaterEqual(freshest, older)

    def test_signal_article_set_prioritizes_us_nato_action_articles(self) -> None:
        payload = {
            "articles": [
                {
                    "id": "generic-1",
                    "title": "Commodity markets react to diplomatic talks",
                    "body": "Investors remain cautious.",
                    "published_at": "2026-04-05T09:00:00Z",
                    "url": "https://marketdesk.test/diplomatic-talks",
                },
                {
                    "id": "signal-1",
                    "title": "Pentagon warns of strike options as NATO aircraft reposition",
                    "body": "US military planners and NATO officials discuss possible attack planning in the Eastern Mediterranean.",
                    "published_at": "2026-04-05T10:00:00Z",
                    "url": "https://examplewire.test/nato-strike-options",
                },
            ]
        }

        articles = parse_articles(payload)
        selected = build_signal_article_set(articles)

        self.assertEqual(selected[0].article_id, "signal-1")
        self.assertTrue(is_us_nato_actor_article(selected[0]))
        self.assertTrue(is_action_indicative_article(selected[0]))
        self.assertTrue(is_us_nato_action_article(selected[0]))

    def test_recent_article_filter_excludes_articles_older_than_two_weeks(self) -> None:
        payload = {
            "articles": [
                {
                    "id": "recent-1",
                    "title": "Pentagon discusses strike options",
                    "published_at": "2026-04-05T10:00:00Z",
                    "url": "https://examplewire.test/recent",
                },
                {
                    "id": "stale-1",
                    "title": "Old NATO warning recap",
                    "published_at": "2026-03-20T10:00:00Z",
                    "url": "https://examplewire.test/stale",
                },
            ]
        }

        articles = parse_articles(payload)
        recent_articles = filter_recent_articles(articles)

        self.assertEqual(len(recent_articles), 1)
        self.assertEqual(recent_articles[0].article_id, "recent-1")


if __name__ == "__main__":
    unittest.main()
