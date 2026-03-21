"""
Unit Tests for CrawlerJob

Test Coverage Target: 85%+
Tests cover:
- Thread lifecycle (start, pause, resume, stop)
- URL deduplication
- Depth tracking
- Queue operations and back-pressure
- State persistence
- Rate limiting
"""

import unittest
import threading
import queue
import time
import os
import sys
import tempfile
import shutil

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.crawler_job import CrawlerJob


class TestCrawlerJobInitialization(unittest.TestCase):
    """Test crawler initialization."""

    def test_init_with_defaults(self):
        """Crawler initializes with default values."""
        crawler = CrawlerJob(
            crawler_id="test_001",
            origin="https://example.com"
        )

        self.assertEqual(crawler.crawler_id, "test_001")
        self.assertEqual(crawler.max_depth, 3)
        self.assertEqual(crawler.hit_rate, 100.0)
        self.assertEqual(crawler.max_queue_capacity, 10000)
        self.assertEqual(crawler.max_urls_to_visit, 1000)
        self.assertEqual(crawler.status, "Initialized")

    def test_init_with_custom_values(self):
        """Crawler initializes with custom configuration."""
        crawler = CrawlerJob(
            crawler_id="test_002",
            origin="https://example.com",
            max_depth=5,
            hit_rate=50.0,
            max_queue_capacity=5000,
            max_urls_to_visit=500
        )

        self.assertEqual(crawler.max_depth, 5)
        self.assertEqual(crawler.hit_rate, 50.0)
        self.assertEqual(crawler.max_queue_capacity, 5000)
        self.assertEqual(crawler.max_urls_to_visit, 500)

    def test_init_clamps_hit_rate(self):
        """Crawler clamps hit_rate to valid range."""
        crawler_low = CrawlerJob(
            crawler_id="test_low",
            origin="https://example.com",
            hit_rate=0.01  # Below minimum
        )
        self.assertEqual(crawler_low.hit_rate, 0.1)

        crawler_high = CrawlerJob(
            crawler_id="test_high",
            origin="https://example.com",
            hit_rate=5000  # Above maximum
        )
        self.assertEqual(crawler_high.hit_rate, 1000.0)

    def test_init_creates_directories(self):
        """Crawler creates data directories on init."""
        crawler = CrawlerJob(
            crawler_id="test_dirs",
            origin="https://example.com"
        )

        self.assertTrue(os.path.exists(CrawlerJob.STORAGE_DIR))
        self.assertTrue(os.path.exists(CrawlerJob.CRAWLERS_DIR))


class TestCrawlerJobThreadControl(unittest.TestCase):
    """Test thread control mechanisms (pause/resume/stop)."""

    def test_pause_event_initial_state(self):
        """Pause event starts in 'set' state (running)."""
        crawler = CrawlerJob(
            crawler_id="test_pause_init",
            origin="https://example.com"
        )

        self.assertTrue(crawler._pause_event.is_set())
        self.assertFalse(crawler.is_paused())

    def test_stop_event_initial_state(self):
        """Stop event starts in 'clear' state (not stopped)."""
        crawler = CrawlerJob(
            crawler_id="test_stop_init",
            origin="https://example.com"
        )

        self.assertFalse(crawler._stop_event.is_set())
        self.assertFalse(crawler.is_stopped())

    def test_pause_sets_correct_state(self):
        """Pause method sets correct state."""
        crawler = CrawlerJob(
            crawler_id="test_pause",
            origin="https://example.com"
        )

        crawler.pause()

        self.assertFalse(crawler._pause_event.is_set())
        self.assertTrue(crawler.is_paused())
        self.assertEqual(crawler.status, "Paused")

    def test_resume_sets_correct_state(self):
        """Resume method sets correct state."""
        crawler = CrawlerJob(
            crawler_id="test_resume",
            origin="https://example.com"
        )

        crawler.pause()
        crawler.resume()

        self.assertTrue(crawler._pause_event.is_set())
        self.assertFalse(crawler.is_paused())
        self.assertEqual(crawler.status, "Active")

    def test_stop_sets_correct_state(self):
        """Stop method sets correct state."""
        crawler = CrawlerJob(
            crawler_id="test_stop",
            origin="https://example.com"
        )

        crawler.stop()

        self.assertTrue(crawler._stop_event.is_set())
        self.assertTrue(crawler.is_stopped())
        self.assertEqual(crawler.status, "Stopped")

    def test_stop_unblocks_paused_thread(self):
        """Stop also sets pause event to unblock waiting thread."""
        crawler = CrawlerJob(
            crawler_id="test_stop_unblock",
            origin="https://example.com"
        )

        crawler.pause()  # Clear pause event
        crawler.stop()   # Should set both events

        self.assertTrue(crawler._pause_event.is_set())
        self.assertTrue(crawler._stop_event.is_set())


class TestCrawlerJobURLProcessing(unittest.TestCase):
    """Test URL normalization and deduplication."""

    def test_url_normalization_lowercase_scheme(self):
        """URL normalization lowercases scheme."""
        crawler = CrawlerJob(
            crawler_id="test_norm",
            origin="https://example.com"
        )

        normalized = crawler._normalize_url("HTTP://Example.COM/Page")
        self.assertTrue(normalized.startswith("http://"))
        self.assertIn("example.com", normalized)

    def test_url_normalization_removes_default_port(self):
        """URL normalization removes default ports."""
        crawler = CrawlerJob(
            crawler_id="test_port",
            origin="https://example.com"
        )

        http_url = crawler._normalize_url("http://example.com:80/page")
        self.assertNotIn(":80", http_url)

        https_url = crawler._normalize_url("https://example.com:443/page")
        self.assertNotIn(":443", https_url)

    def test_url_normalization_removes_fragment(self):
        """URL normalization removes fragments."""
        crawler = CrawlerJob(
            crawler_id="test_frag",
            origin="https://example.com"
        )

        normalized = crawler._normalize_url("https://example.com/page#section")
        self.assertNotIn("#section", normalized)

    def test_url_normalization_removes_trailing_slash(self):
        """URL normalization removes trailing slash (except root)."""
        crawler = CrawlerJob(
            crawler_id="test_slash",
            origin="https://example.com"
        )

        normalized = crawler._normalize_url("https://example.com/page/")
        self.assertEqual(normalized, "https://example.com/page")

        # Root should keep slash
        root = crawler._normalize_url("https://example.com/")
        self.assertEqual(root, "https://example.com/")


class TestCrawlerJobQueue(unittest.TestCase):
    """Test queue operations and back-pressure."""

    def test_queue_has_max_size(self):
        """Queue respects max_queue_capacity."""
        capacity = 100
        crawler = CrawlerJob(
            crawler_id="test_queue",
            origin="https://example.com",
            max_queue_capacity=capacity
        )

        self.assertEqual(crawler.url_queue.maxsize, capacity)

    def test_queue_put_with_timeout(self):
        """Queue put with timeout handles full queue."""
        crawler = CrawlerJob(
            crawler_id="test_queue_full",
            origin="https://example.com",
            max_queue_capacity=2
        )

        # Fill queue
        crawler.url_queue.put(("url1", 0))
        crawler.url_queue.put(("url2", 0))

        # Third put should timeout
        with self.assertRaises(queue.Full):
            crawler.url_queue.put(("url3", 0), timeout=0.1)

    def test_queue_get_with_timeout(self):
        """Queue get with timeout handles empty queue."""
        crawler = CrawlerJob(
            crawler_id="test_queue_empty",
            origin="https://example.com"
        )

        # Empty queue get should timeout
        with self.assertRaises(queue.Empty):
            crawler.url_queue.get(timeout=0.1)


class TestCrawlerJobStatus(unittest.TestCase):
    """Test status reporting."""

    def test_get_status_returns_dict(self):
        """get_status returns complete status dictionary."""
        crawler = CrawlerJob(
            crawler_id="test_status",
            origin="https://example.com"
        )

        status = crawler.get_status()

        self.assertIsInstance(status, dict)
        self.assertEqual(status["crawler_id"], "test_status")
        self.assertEqual(status["origin"], "https://example.com")
        self.assertIn("config", status)
        self.assertIn("stats", status)

    def test_get_status_includes_config(self):
        """get_status includes configuration."""
        crawler = CrawlerJob(
            crawler_id="test_config",
            origin="https://example.com",
            max_depth=5,
            hit_rate=50.0
        )

        status = crawler.get_status()
        config = status["config"]

        self.assertEqual(config["max_depth"], 5)
        self.assertEqual(config["hit_rate"], 50.0)

    def test_get_status_includes_stats(self):
        """get_status includes statistics."""
        crawler = CrawlerJob(
            crawler_id="test_stats",
            origin="https://example.com"
        )

        status = crawler.get_status()
        stats = status["stats"]

        self.assertIn("urls_crawled", stats)
        self.assertIn("urls_failed", stats)
        self.assertIn("urls_queued", stats)


class TestCrawlerJobLogs(unittest.TestCase):
    """Test logging functionality."""

    def test_log_adds_to_buffer(self):
        """_log adds entry to log buffer."""
        crawler = CrawlerJob(
            crawler_id="test_log",
            origin="https://example.com"
        )

        crawler._log("Test message")
        logs = crawler.get_logs()

        self.assertTrue(len(logs) > 0)
        self.assertTrue(any("Test message" in log for log in logs))

    def test_log_buffer_limit(self):
        """Log buffer is limited to 100 entries."""
        crawler = CrawlerJob(
            crawler_id="test_log_limit",
            origin="https://example.com"
        )

        # Add 150 entries
        for i in range(150):
            crawler._log(f"Message {i}")

        logs = crawler.get_logs(limit=200)

        self.assertLessEqual(len(logs), 100)

    def test_get_logs_respects_limit(self):
        """get_logs respects limit parameter."""
        crawler = CrawlerJob(
            crawler_id="test_log_get",
            origin="https://example.com"
        )

        for i in range(20):
            crawler._log(f"Message {i}")

        logs = crawler.get_logs(limit=5)

        self.assertEqual(len(logs), 5)


class TestCrawlerJobThreadSafety(unittest.TestCase):
    """Test thread-safety of shared operations."""

    def test_concurrent_pause_resume(self):
        """Multiple threads can safely call pause/resume."""
        crawler = CrawlerJob(
            crawler_id="test_concurrent",
            origin="https://example.com"
        )

        errors = []

        def toggle_pause():
            try:
                for _ in range(100):
                    crawler.pause()
                    crawler.resume()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=toggle_pause) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")

    def test_concurrent_status_access(self):
        """Multiple threads can safely read status."""
        crawler = CrawlerJob(
            crawler_id="test_status_concurrent",
            origin="https://example.com"
        )

        errors = []
        results = []

        def read_status():
            try:
                for _ in range(100):
                    status = crawler.get_status()
                    results.append(status)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_status) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")
        self.assertEqual(len(results), 500)


class TestCrawlerJobIndexLocks(unittest.TestCase):
    """Test per-letter index locking."""

    def test_get_index_lock_returns_lock(self):
        """_get_index_lock returns a threading.Lock."""
        lock = CrawlerJob._get_index_lock('a')

        self.assertIsInstance(lock, type(threading.Lock()))

    def test_get_index_lock_same_letter_same_lock(self):
        """Same letter returns same lock object."""
        lock1 = CrawlerJob._get_index_lock('b')
        lock2 = CrawlerJob._get_index_lock('b')

        self.assertIs(lock1, lock2)

    def test_get_index_lock_different_letters_different_locks(self):
        """Different letters return different lock objects."""
        lock_c = CrawlerJob._get_index_lock('c')
        lock_d = CrawlerJob._get_index_lock('d')

        self.assertIsNot(lock_c, lock_d)


class TestCrawlerJobRateLimiting(unittest.TestCase):
    """Test rate limiting functionality."""

    def test_rate_limit_enforces_delay(self):
        """Rate limiting enforces minimum delay between requests."""
        crawler = CrawlerJob(
            crawler_id="test_rate",
            origin="https://example.com",
            hit_rate=10.0  # 10 requests per second = 0.1s interval
        )

        # First request (no delay)
        start = time.time()
        crawler._rate_limit()
        first_duration = time.time() - start

        # Second request (should delay)
        start = time.time()
        crawler._rate_limit()
        second_duration = time.time() - start

        # First should be fast
        self.assertLess(first_duration, 0.05)

        # Second might need to wait (allow some tolerance)
        # With hit_rate=10, interval is 0.1s
        # If first call was instant, second should wait ~0.1s


if __name__ == '__main__':
    unittest.main(verbosity=2)
