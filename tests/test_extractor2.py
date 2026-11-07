"""Unit tests for extractor2. Stdlib unittest — run: python -m unittest discover -s tests -v"""

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from extractor2 import (
    SOURCES,
    Story,
    dedupe,
    decrypt,
    encrypt,
    fetch_all_sources,
    format_digest,
    jaccard,
    normalise_title,
    parse_feed,
)


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title>
<item><title>Big AI breakthrough announced today</title><link>http://x/1</link>
<pubDate>Fri, 07 Nov 2026 19:00:00 +0000</pubDate><guid>http://x/1</guid></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>T</title>
<entry><title>Atom story one</title><link href="http://x/a"/><published>2026-11-07T19:00:00Z</published></entry>
</feed>"""


class TestParse(unittest.TestCase):
    def test_rss_items(self):
        stories = parse_feed(RSS, "TestSrc", "tech")
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0].title, "Big AI breakthrough announced today")
        self.assertEqual(stories[0].source, "TestSrc")
        self.assertIsNotNone(stories[0].published)

    def test_atom_entries(self):
        stories = parse_feed(ATOM, "AtomSrc", "ai")
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0].link, "http://x/a")

    def test_malformed_xml_returns_empty(self):
        self.assertEqual(parse_feed(b"<not xml", "S", "tech"), [])


class TestDedupe(unittest.TestCase):
    def test_same_story_three_sources_groups(self):
        stories = [Story("OpenAI announces new model", "http://a", "A", "tech", None),
                   Story("OpenAI announces new model", "http://b", "B", "tech", None),
                   Story("OpenAI announces new model", "http://c", "C", "tech", None)]
        ranked = dedupe(stories)
        self.assertEqual(len(ranked), 1)
        best, n = ranked[0]
        self.assertEqual(n, 3)

    def test_different_stories_stay_separate(self):
        stories = [Story("Cats cure cancer", "http://a", "A", "tech", None),
                   Story("New battery ships", "http://b", "B", "tech", None)]
        self.assertEqual(len(dedupe(stories)), 2)

    def test_title_normalisation(self):
        from extractor2 import normalise_title
        self.assertEqual(normalise_title("The Next-Gen Chip!"), "next gen chip")

    def test_jaccard_identical_and_disjoint(self):
        from extractor2 import jaccard
        self.assertEqual(jaccard("a b c", "a b c"), 1.0)
        self.assertEqual(jaccard("a b", "c d"), 0.0)

    def test_sorted_by_coverage_then_recency(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        stories = [Story("Lone story", "http://a", "A", "tech", now),
                   Story("Popular story", "http://b", "B", "tech", now - timedelta(hours=5)),
                   Story("Popular story", "http://c", "C", "tech", now - timedelta(hours=6))]
        ranked = dedupe(stories)
        self.assertEqual(ranked[0][1], 2)
        self.assertEqual(ranked[1][1], 1)


class TestSecrets(unittest.TestCase):
    def test_roundtrip(self):
        blob = encrypt("pw", '{"token": "1:2", "chat_id": "42"}')
        self.assertNotIn("1:2", blob)
        self.assertEqual(decrypt("pw", blob), '{"token": "1:2", "chat_id": "42"}')


class TestSources(unittest.TestCase):
    def test_at_least_20_sources(self):
        self.assertGreaterEqual(len(SOURCES), 20)

    def test_source_shape(self):
        for name, url, cat in SOURCES:
            self.assertTrue(name and url.startswith("http"))
            self.assertIn(cat, ("tech", "security", "ai"))


class TestFetchResilience(unittest.TestCase):
    def test_one_dead_source_others_ok(self):
        def fake_fetch(url, timeout=25):
            if "dead" in url:
                raise RuntimeError("down")
            return RSS
        dead_sources = [("Dead", "http://dead/feed", "tech"), ("Good", "http://good/feed", "tech")]
        with patch("extractor2.SOURCES", dead_sources), \
             patch("extractor2._fetch", side_effect=fake_fetch):
            stories = fetch_all_sources()
        self.assertEqual(len(stories), 1)


class TestFormat(unittest.TestCase):
    def test_digest_shows_coverage_and_caps(self):
        from extractor2 import format_digest, Story
        ranked = [(Story(f"Story {i}", "http://x", "S", "tech", None), i % 3 + 1) for i in range(60)]
        out = format_digest(ranked, top_n=25)
        self.assertLessEqual(len(out), 4000)
        self.assertIn("x2", out)


if __name__ == "__main__":
    unittest.main()
