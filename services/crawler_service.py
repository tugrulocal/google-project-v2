"""
Crawler Service - Manages CrawlerJob lifecycle and state.

This service provides:
- Crawler creation and configuration
- Pause/Resume/Stop operations
- Status monitoring
- Resume from saved files
- Statistics aggregation
"""

import os
import json
import threading
import urllib.parse
from typing import Dict, List, Optional

# Import CrawlerJob from utils
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.crawler_job import CrawlerJob


class CrawlerService:
    """
    Service layer for managing crawler instances.

    Thread-Safety:
    - Uses lock to protect active_crawlers dictionary
    - Each CrawlerJob manages its own thread-safety internally
    """

    # Data directories (same as CrawlerJob)
    DATA_DIR = "data"
    CRAWLERS_DIR = os.path.join(DATA_DIR, "crawlers")
    STORAGE_DIR = os.path.join(DATA_DIR, "storage")
    VISITED_FILE = os.path.join(DATA_DIR, "visited_urls.data")

    def __init__(self):
        """Initialize the crawler service."""
        self._lock = threading.Lock()
        self.active_crawlers: Dict[str, CrawlerJob] = {}

        # Ensure directories exist
        os.makedirs(self.CRAWLERS_DIR, exist_ok=True)
        os.makedirs(self.STORAGE_DIR, exist_ok=True)

    def create_crawler(
        self,
        origin: str,
        max_depth: int = 3,
        hit_rate: float = 100.0,
        max_queue_capacity: int = 10000,
        max_urls_to_visit: int = 1000,
        same_domain_only: bool = True,
        include_subdomains: bool = False,
        allowed_paths: list = None,
        blocked_patterns: list = None
    ) -> Dict:
        """
        Create and start a new crawler.

        Args:
            origin: Seed URL to start crawling from
            max_depth: Maximum depth to crawl (1-1000)
            hit_rate: Requests per second (0.1-1000)
            max_queue_capacity: Maximum queue size (100-100000)
            max_urls_to_visit: Maximum URLs to visit (0-10000)
            same_domain_only: Only crawl URLs from same domain
            include_subdomains: Also crawl subdomains (when same_domain_only=True)
            allowed_paths: List of allowed path prefixes
            blocked_patterns: List of blocked URL patterns

        Returns:
            Dict with crawler_id and status
        """
        # Validate parameters
        if not origin or not origin.startswith(('http://', 'https://')):
            raise ValueError("Invalid origin URL. Must start with http:// or https://")

        max_depth = max(1, min(max_depth, 1000))
        hit_rate = max(0.1, min(hit_rate, 1000.0))
        max_queue_capacity = max(100, min(max_queue_capacity, 100000))
        max_urls_to_visit = max(1, min(max_urls_to_visit, 10000))

        # Generate crawler ID based on domain
        parsed_origin = urllib.parse.urlparse(origin)
        base_domain = parsed_origin.netloc
        if base_domain.startswith('www.'):
            base_domain = base_domain[4:]
        
        base_crawler_id = base_domain if base_domain else "crawler"
        crawler_id = base_crawler_id
        counter = 1

        # Use lock early to safely find a unique ID and track it immediately
        with self._lock:
            # Check active crawlers and existing files to ensure uniqueness
            while crawler_id in self.active_crawlers or os.path.exists(os.path.join(self.CRAWLERS_DIR, f"{crawler_id}.data")):
                crawler_id = f"{base_crawler_id}_{counter}"
                counter += 1

            # Create crawler instance
            crawler = CrawlerJob(
                crawler_id=crawler_id,
                origin=origin,
                max_depth=max_depth,
                hit_rate=hit_rate,
                max_queue_capacity=max_queue_capacity,
                max_urls_to_visit=max_urls_to_visit,
                resume_from_files=False,
                same_domain_only=same_domain_only,
                include_subdomains=include_subdomains,
                allowed_paths=allowed_paths,
                blocked_patterns=blocked_patterns
            )

            # Track and start
            self.active_crawlers[crawler_id] = crawler
        
        crawler.start()
        
        return {
            "crawler_id": crawler_id,
            "origin": origin,
            "k": max_depth,
            "status": "Active"
        }

    def get_crawler_status(self, crawler_id: str) -> Optional[Dict]:
        """
        Get status of a specific crawler.

        Args:
            crawler_id: The crawler identifier

        Returns:
            Status dict or None if not found
        """
        # Check active crawlers first
        with self._lock:
            crawler = self.active_crawlers.get(crawler_id)

        if crawler and crawler.is_alive():
            status = crawler.get_status()
            status["logs"] = crawler.get_logs(50)
            return status

        # Try loading from file
        status_path = os.path.join(self.CRAWLERS_DIR, f"{crawler_id}.data")
        if os.path.exists(status_path):
            try:
                with open(status_path, 'r', encoding='utf-8') as f:
                    status = json.load(f)

                # Load logs
                logs_path = os.path.join(self.CRAWLERS_DIR, f"{crawler_id}.logs")
                if os.path.exists(logs_path):
                    with open(logs_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        status["logs"] = [line.strip() for line in lines[-50:]]
                else:
                    status["logs"] = []

                # Check if thread is dead but was active
                if status.get("status") == "Active":
                    status["status"] = "Stopped"

                return status
            except Exception:
                pass

        return None

    def list_crawlers(self) -> List[Dict]:
        """
        List all crawlers (active and saved).

        Returns:
            List of crawler status dicts
        """
        crawlers = []
        seen_ids = set()

        # Active crawlers
        with self._lock:
            for crawler_id, crawler in list(self.active_crawlers.items()):
                if crawler.is_alive():
                    status = crawler.get_status()
                    crawlers.append(status)
                    seen_ids.add(crawler_id)
                else:
                    # Clean up dead reference
                    del self.active_crawlers[crawler_id]

        # Saved crawlers
        if os.path.exists(self.CRAWLERS_DIR):
            for filename in os.listdir(self.CRAWLERS_DIR):
                if filename.endswith('.data'):
                    crawler_id = filename[:-5]  # Remove .data
                    if crawler_id not in seen_ids:
                        try:
                            with open(os.path.join(self.CRAWLERS_DIR, filename), 'r', encoding='utf-8') as f:
                                status = json.load(f)
                                # Mark as stopped if was active
                                if status.get("status") == "Active":
                                    status["status"] = "Stopped"
                                crawlers.append(status)
                        except Exception:
                            pass

        # Sort by created_at descending
        crawlers.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return crawlers

    def pause_crawler(self, crawler_id: str) -> Dict:
        """
        Pause an active crawler.

        Args:
            crawler_id: The crawler identifier

        Returns:
            Status dict
        """
        with self._lock:
            crawler = self.active_crawlers.get(crawler_id)

        if not crawler or not crawler.is_alive():
            raise ValueError(f"Crawler {crawler_id} is not active")

        if crawler.is_paused():
            return {"status": "Already Paused"}

        crawler.pause()
        return {"status": "Paused"}

    def resume_crawler(self, crawler_id: str) -> Dict:
        """
        Resume a paused crawler.

        Args:
            crawler_id: The crawler identifier

        Returns:
            Status dict
        """
        with self._lock:
            crawler = self.active_crawlers.get(crawler_id)

        if crawler and crawler.is_alive():
            if not crawler.is_paused():
                return {"status": "Already Active"}
            crawler.resume()
            return {"status": "Active"}

        # Try to resume from files
        return self.resume_from_files(crawler_id)

    def stop_crawler(self, crawler_id: str) -> Dict:
        """
        Stop an active crawler.

        Args:
            crawler_id: The crawler identifier

        Returns:
            Status dict
        """
        with self._lock:
            crawler = self.active_crawlers.get(crawler_id)

        if not crawler or not crawler.is_alive():
            raise ValueError(f"Crawler {crawler_id} is not active")

        crawler.stop()

        # Wait briefly for thread to acknowledge stop
        crawler.join(timeout=2.0)

        return {"status": "Stopped"}

    def delete_crawler(self, crawler_id: str) -> Dict:
        """
        Delete a crawler and its associated files.

        Args:
            crawler_id: The crawler identifier

        Returns:
            Status dict with deleted files
        """
        # Stop if running
        with self._lock:
            crawler = self.active_crawlers.get(crawler_id)
            if crawler and crawler.is_alive():
                crawler.stop()
                crawler.join(timeout=2.0)
            if crawler_id in self.active_crawlers:
                del self.active_crawlers[crawler_id]

        # Delete associated files
        files_deleted = []
        for ext in ['.data', '.logs', '.queue']:
            path = os.path.join(self.CRAWLERS_DIR, f"{crawler_id}{ext}")
            if os.path.exists(path):
                try:
                    os.remove(path)
                    files_deleted.append(f"{crawler_id}{ext}")
                except Exception:
                    pass

        if not files_deleted:
            raise ValueError(f"Crawler {crawler_id} not found")

        return {
            "status": "deleted",
            "crawler_id": crawler_id,
            "files_deleted": files_deleted
        }

    def resume_from_files(self, crawler_id: str) -> Dict:
        """
        Resume a stopped crawler from saved files.

        Args:
            crawler_id: The crawler identifier

        Returns:
            Status dict with new status
        """
        # Load saved configuration
        status_path = os.path.join(self.CRAWLERS_DIR, f"{crawler_id}.data")
        if not os.path.exists(status_path):
            raise ValueError(f"No saved state found for crawler {crawler_id}")

        with open(status_path, 'r', encoding='utf-8') as f:
            saved_state = json.load(f)

        config = saved_state.get("config", {})

        # Create new crawler with resume flag
        crawler = CrawlerJob(
            crawler_id=crawler_id,
            origin=saved_state.get("origin", ""),
            max_depth=config.get("max_depth", 3),
            hit_rate=config.get("hit_rate", 100.0),
            max_queue_capacity=config.get("max_queue_capacity", 10000),
            max_urls_to_visit=config.get("max_urls_to_visit", 1000),
            resume_from_files=True,
            same_domain_only=config.get("same_domain_only", True),
            include_subdomains=config.get("include_subdomains", False),
            allowed_paths=config.get("allowed_paths"),
            blocked_patterns=config.get("blocked_patterns")
        )

        # Track and start
        with self._lock:
            self.active_crawlers[crawler_id] = crawler

        crawler.start()

        return {"status": "Active", "message": "Resumed from saved state"}

    def clear_all_data(self) -> Dict:
        """
        Clear all crawler data and stop active crawlers.

        Returns:
            Status dict
        """
        # Stop all active crawlers
        with self._lock:
            for crawler in self.active_crawlers.values():
                if crawler.is_alive():
                    crawler.stop()
            self.active_crawlers.clear()

        # Clear files
        import shutil

        if os.path.exists(self.CRAWLERS_DIR):
            shutil.rmtree(self.CRAWLERS_DIR)
            os.makedirs(self.CRAWLERS_DIR)

        if os.path.exists(self.STORAGE_DIR):
            shutil.rmtree(self.STORAGE_DIR)
            os.makedirs(self.STORAGE_DIR)

        if os.path.exists(self.VISITED_FILE):
            os.remove(self.VISITED_FILE)

        return {"status": "success", "message": "All data cleared"}

    def get_statistics(self) -> Dict:
        """
        Get aggregate statistics across all crawlers.

        Returns:
            Statistics dict
        """
        stats = {
            "total_crawlers": 0,
            "active_crawlers": 0,
            "paused_crawlers": 0,
            "total_urls_crawled": 0,
            "total_words_indexed": 0,
            "storage_size_bytes": 0
        }

        # Count crawlers
        crawlers = self.list_crawlers()
        stats["total_crawlers"] = len(crawlers)

        for crawler in crawlers:
            status = crawler.get("status", "")
            if status == "Active":
                stats["active_crawlers"] += 1
            elif status == "Paused":
                stats["paused_crawlers"] += 1

            crawler_stats = crawler.get("stats", {})
            stats["total_urls_crawled"] += crawler_stats.get("urls_crawled", 0)

        # Count indexed words
        if os.path.exists(self.STORAGE_DIR):
            for filename in os.listdir(self.STORAGE_DIR):
                filepath = os.path.join(self.STORAGE_DIR, filename)
                if os.path.isfile(filepath):
                    stats["storage_size_bytes"] += os.path.getsize(filepath)
                    # Count lines (approximate word count)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            stats["total_words_indexed"] += sum(1 for _ in f)
                    except Exception:
                        pass

        return stats


# Singleton instance
_service_instance: Optional[CrawlerService] = None
_service_lock = threading.Lock()


def get_crawler_service() -> CrawlerService:
    """Get or create the crawler service singleton."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = CrawlerService()
    return _service_instance
