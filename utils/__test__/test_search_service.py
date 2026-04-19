"""
Unit Tests for SearchService

Focus:
- HW2 triple contract compatibility
- Backward-compatible rich result fields
- Basic search behavior on letter-partitioned index files
"""

import os
import shutil
import tempfile
import unittest

from services.search_service import SearchService


class TestSearchService(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="search_service_test_")
        self.original_storage_dir = SearchService.STORAGE_DIR
        SearchService.STORAGE_DIR = self.tmpdir
        self.service = SearchService()

    def tearDown(self):
        SearchService.STORAGE_DIR = self.original_storage_dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_index_lines(self, letter, lines):
        path = os.path.join(self.tmpdir, f"{letter}.data")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def test_empty_query_returns_empty_triples(self):
        result = self.service.search("  ")
        self.assertIn("triples", result)
        self.assertEqual(result["triples"], [])
        self.assertEqual(result["results"], [])

    def test_search_returns_hw2_triples(self):
        self._write_index_lines(
            "p",
            [
                "python https://docs.python.org https://python.org 1 5",
                "python https://realpython.com https://python.org 2 2",
            ],
        )

        result = self.service.search("python", page_limit=10, page_offset=0)

        self.assertGreaterEqual(result["total_results"], 1)
        self.assertIn("triples", result)
        first_triple = result["triples"][0]
        self.assertEqual(len(first_triple), 3)
        self.assertIsInstance(first_triple[0], str)
        self.assertIsInstance(first_triple[1], str)
        self.assertIsInstance(first_triple[2], int)

    def test_results_keep_backward_compatible_fields(self):
        self._write_index_lines(
            "a",
            ["agent https://example.com/page https://example.com 0 3"],
        )

        result = self.service.search("agent")
        item = result["results"][0]

        self.assertIn("url", item)
        self.assertIn("origin", item)
        self.assertIn("depth", item)
        self.assertIn("relevant_url", item)
        self.assertIn("origin_url", item)
        self.assertEqual(item["relevant_url"], item["url"])
        self.assertEqual(item["origin_url"], item["origin"])

    def test_multi_word_query_uses_and_logic(self):
        self._write_index_lines(
            "p",
            [
                "python https://site-a.com https://seed.com 1 3",
                "python https://site-b.com https://seed.com 1 3",
            ],
        )
        self._write_index_lines(
            "t",
            [
                "threading https://site-a.com https://seed.com 1 2",
                "threading https://site-c.com https://seed.com 1 2",
            ],
        )

        result = self.service.search("python threading")
        urls = {row[0] for row in result["triples"]}

        self.assertEqual(urls, {"https://site-a.com"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
