"""
CrawlerJob - Multi-threaded Web Crawler with Pause/Resume/Stop Support

Thread-Safety Overview:
=======================
This module implements a thread-safe web crawler using Python's native
threading primitives. Key synchronization mechanisms:

1. threading.Event: Non-blocking signals for pause/stop control
2. queue.Queue: Thread-safe FIFO with built-in locking
3. threading.Lock: Protects shared mutable state (visited_urls, stats)
4. Atomic file operations: Write-temp-then-rename pattern

Back-Pressure Strategy:
=======================
- queue.Queue(maxsize=N): Blocks/times out when full
- max_urls_to_visit: Hard limit on crawl session
- hit_rate: Rate limiting via time-based throttling
"""

import threading
import queue
import urllib.request
import urllib.parse
import urllib.error
import urllib.robotparser
import ssl
import os
import json
import re
import time
import logging
from html.parser import HTMLParser
from collections import Counter
from datetime import datetime
from typing import Optional, Tuple, List, Set, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# =============================================================================
# SECTION 1: HTML Parser (Thread-Safe by Design)
# =============================================================================
# HTMLParser is instantiated fresh for each URL, so no shared state.
# Each CrawlerJob thread creates its own parser instance.
# =============================================================================

class CrawlerHTMLParser(HTMLParser):
    """
    Custom HTML parser for extracting links and text content.

    Thread-Safety: SAFE
    - Instantiated per-URL (no shared state between threads)
    - All state is instance-local
    """

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: List[str] = []
        self.text_content: List[str] = []
        self.title: str = ""
        self._in_script = False
        self._in_style = False
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list):
        tag = tag.lower()
        if tag == 'script':
            self._in_script = True
        elif tag == 'style':
            self._in_style = True
        elif tag == 'title':
            self._in_title = True
        elif tag == 'a':
            for attr, value in attrs:
                if attr.lower() == 'href' and value:
                    abs_url = self._resolve_url(value)
                    if abs_url and self._is_valid_url(abs_url):
                        self.links.append(abs_url)

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag == 'script':
            self._in_script = False
        elif tag == 'style':
            self._in_style = False
        elif tag == 'title':
            self._in_title = False

    def handle_data(self, data: str):
        if self._in_title:
            self.title += data.strip()
        elif not self._in_script and not self._in_style:
            text = data.strip()
            if text:
                self.text_content.append(text)

    def _resolve_url(self, url: str) -> Optional[str]:
        """Resolve relative URL to absolute."""
        try:
            # Skip fragments and javascript
            if url.startswith('#') or url.startswith('javascript:'):
                return None
            return urllib.parse.urljoin(self.base_url, url)
        except Exception:
            return None

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is HTTP/HTTPS."""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
        except Exception:
            return False

    def get_text(self) -> str:
        """Return combined text content."""
        return ' '.join(self.text_content)

    def get_links(self) -> List[str]:
        """Return deduplicated list of valid links."""
        return list(set(self.links))

    def get_title(self) -> str:
        """Return page title."""
        return self.title.strip()


# =============================================================================
# SECTION 2: CrawlerJob Main Class
# =============================================================================

class CrawlerJob(threading.Thread):
    """
    Multi-threaded web crawler with pause/resume/stop capability.

    Thread-Safety Mechanisms:
    -------------------------
    1. _pause_event (threading.Event):
       - .set() = running, .clear() = paused
       - .wait() blocks thread until set
       - Thread-safe by design (internal locking)

    2. _stop_event (threading.Event):
       - .set() signals thread to terminate
       - Checked non-blocking with .is_set()
       - Thread-safe by design

    3. url_queue (queue.Queue):
       - maxsize enforces back-pressure
       - .put()/.get() are atomic operations
       - Timeout prevents deadlocks

    4. _lock (threading.Lock):
       - Protects: visited_urls, stats counters
       - Used for read-modify-write operations

    5. File I/O:
       - Atomic write: temp file + os.replace()
       - Per-letter locks prevent interleaving
    """

    # Class-level lock for index file writes (shared across instances)
    _index_locks: Dict[str, threading.Lock] = {}
    _index_locks_lock = threading.Lock()

    # Data directories
    DATA_DIR = "data"
    STORAGE_DIR = os.path.join(DATA_DIR, "storage")
    CRAWLERS_DIR = os.path.join(DATA_DIR, "crawlers")
    VISITED_FILE = os.path.join(DATA_DIR, "visited_urls.data")

    def __init__(
        self,
        crawler_id: str,
        origin: str,
        max_depth: int = 3,
        hit_rate: float = 100.0,
        max_queue_capacity: int = 10000,
        max_urls_to_visit: int = 1000,
        resume_from_files: bool = False,
        same_domain_only: bool = True,
        include_subdomains: bool = False,
        allowed_paths: Optional[List[str]] = None,
        blocked_patterns: Optional[List[str]] = None
    ):
        """
        Initialize crawler with configuration.

        Thread-Safety: SAFE
        - Called from main thread before start()
        - No concurrent access during initialization

        Domain Filtering Parameters:
        - same_domain_only: If True, only crawl URLs from the same domain as origin
        - include_subdomains: If True and same_domain_only=True, also crawl subdomains
        - allowed_paths: List of path prefixes to allow (e.g., ['/docs/', '/api/'])
        - blocked_patterns: List of patterns to block (e.g., ['tracking', 'analytics'])
        """
        super().__init__(daemon=True)

        # Configuration (immutable after init)
        self.crawler_id = crawler_id
        self.origin = self._normalize_url(origin)
        self.max_depth = max_depth
        self.hit_rate = max(0.1, min(hit_rate, 1000.0))  # Clamp to valid range
        self.max_queue_capacity = max_queue_capacity
        self.max_urls_to_visit = max_urls_to_visit
        self.resume_from_files = resume_from_files

        # Domain filtering configuration
        self.same_domain_only = same_domain_only
        self.include_subdomains = include_subdomains
        self.allowed_paths = allowed_paths or []
        self.blocked_patterns = blocked_patterns or []

        # Extract origin domain for filtering
        parsed_origin = urllib.parse.urlparse(self.origin)
        self._origin_domain = parsed_origin.netloc.lower()
        # Extract base domain (e.g., "example.com" from "www.example.com")
        domain_parts = self._origin_domain.split('.')
        self._base_domain = '.'.join(domain_parts[-2:]) if len(domain_parts) >= 2 else self._origin_domain

        # =====================================================================
        # Thread Control Events
        # =====================================================================
        # THREAD-SAFETY: Events use internal locks, safe for cross-thread access
        #
        # _pause_event:
        #   - .set() means "running" (thread proceeds)
        #   - .clear() means "paused" (thread blocks on .wait())
        #   - Initial state: set (running)
        #
        # _stop_event:
        #   - .set() means "stop requested"
        #   - Initial state: clear (not stopped)
        # =====================================================================
        self._pause_event = threading.Event()
        self._pause_event.set()  # Start in running state

        self._stop_event = threading.Event()
        # _stop_event starts clear (not stopped)

        # =====================================================================
        # Thread-Safe URL Queue (Back-Pressure)
        # =====================================================================
        # THREAD-SAFETY: queue.Queue has internal locking
        # BACK-PRESSURE: maxsize limits memory usage
        #   - put(timeout=1) fails gracefully when full
        #   - get(timeout=1) allows periodic stop checks
        # =====================================================================
        self.url_queue: queue.Queue = queue.Queue(maxsize=max_queue_capacity)

        # =====================================================================
        # Shared Mutable State (Protected by Lock)
        # =====================================================================
        # THREAD-SAFETY: All access to these must hold _lock
        # =====================================================================
        self._lock = threading.Lock()
        self.visited_urls: Set[str] = set()
        self.urls_crawled: int = 0
        self.urls_failed: int = 0
        self.status: str = "Initialized"
        self.created_at: str = datetime.now().isoformat()
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None

        # Rate limiting state
        self._last_request_time: Optional[float] = None
        self._request_interval: float = 1.0 / self.hit_rate

        # SSL contexts
        self._ssl_secure: ssl.SSLContext = None
        self._ssl_permissive: ssl.SSLContext = None
        self._setup_ssl_contexts()

        # Ensure directories exist
        self._ensure_directories()

        # Log buffer for status endpoint
        self._log_buffer: List[str] = []
        self._log_buffer_lock = threading.Lock()
        
        # Robots.txt Parsers Cache
        self._robot_parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._robot_parsers_lock = threading.Lock()

    # =========================================================================
    # SECTION 2.1: SSL Context Setup
    # =========================================================================

    def _setup_ssl_contexts(self):
        """
        Create SSL contexts for HTTPS requests.

        Thread-Safety: SAFE
        - Called once during __init__
        - SSL contexts are immutable after creation
        - Used read-only from run()
        """
        # Secure context (default verification)
        self._ssl_secure = ssl.create_default_context()

        # Permissive context (for sites with certificate issues)
        self._ssl_permissive = ssl.create_default_context()
        self._ssl_permissive.check_hostname = False
        self._ssl_permissive.verify_mode = ssl.CERT_NONE

    # =========================================================================
    # SECTION 2.2: Directory Setup
    # =========================================================================

    def _ensure_directories(self):
        """
        Create data directories if they don't exist.

        Thread-Safety: SAFE
        - os.makedirs with exist_ok=True is atomic
        - Called during init before concurrent access
        """
        os.makedirs(self.STORAGE_DIR, exist_ok=True)
        os.makedirs(self.CRAWLERS_DIR, exist_ok=True)

    # =========================================================================
    # SECTION 2.3: Thread Control Methods (Called from External Threads)
    # =========================================================================

    def pause(self) -> None:
        """
        Pause the crawler.

        Thread-Safety: SAFE
        - Event.clear() is atomic (internal locking)
        - status write protected by _lock

        Behavior:
        - Clears _pause_event, causing run() to block on .wait()
        - Saves current state for potential resume
        """
        self._pause_event.clear()
        with self._lock:
            self.status = "Paused"
        self._log("Crawler paused")
        self._save_state()

    def resume(self) -> None:
        """
        Resume the crawler after pause.

        Thread-Safety: SAFE
        - Event.set() is atomic (internal locking)
        - status write protected by _lock

        Behavior:
        - Sets _pause_event, unblocking run() from .wait()
        """
        with self._lock:
            self.status = "Active"
        self._pause_event.set()
        self._log("Crawler resumed")

    def stop(self) -> None:
        """
        Stop the crawler gracefully.

        Thread-Safety: SAFE
        - Event.set() is atomic
        - Sets both events to ensure thread exits

        Behavior:
        1. Sets _stop_event (signals termination)
        2. Sets _pause_event (unblocks if paused)
        3. Thread will exit on next loop iteration
        """
        self._stop_event.set()
        self._pause_event.set()  # Unblock if waiting on pause
        with self._lock:
            self.status = "Stopped"
        self._log("Stop signal sent")

    def is_paused(self) -> bool:
        """
        Check if crawler is paused.

        Thread-Safety: SAFE
        - Event.is_set() is atomic read
        """
        return not self._pause_event.is_set()

    def is_stopped(self) -> bool:
        """
        Check if stop was requested.

        Thread-Safety: SAFE
        - Event.is_set() is atomic read
        """
        return self._stop_event.is_set()

    # =========================================================================
    # SECTION 2.4: URL Normalization
    # =========================================================================

    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL for consistent comparison.

        Thread-Safety: SAFE
        - Pure function, no shared state
        - Uses only local variables

        Normalization steps:
        1. Parse URL components
        2. Lowercase scheme and host
        3. Remove default ports (80/443)
        4. Remove fragment (#section)
        5. Remove trailing slash (except root)
        """
        try:
            parsed = urllib.parse.urlparse(url)

            # Lowercase scheme and host
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()

            # Remove default ports
            if ':' in netloc:
                host, port = netloc.rsplit(':', 1)
                if (scheme == 'http' and port == '80') or \
                   (scheme == 'https' and port == '443'):
                    netloc = host

            # Remove fragment
            # Keep path and query as-is
            path = parsed.path

            # Remove trailing slash (except for root)
            if path != '/' and path.endswith('/'):
                path = path.rstrip('/')

            # Rebuild URL
            normalized = urllib.parse.urlunparse((
                scheme,
                netloc,
                path,
                parsed.params,
                parsed.query,
                ''  # Remove fragment
            ))

            return normalized
        except Exception:
            return url

    # =========================================================================
    # SECTION 2.4b: URL Domain Filtering
    # =========================================================================

    def _should_crawl_url(self, url: str) -> bool:
        """
        Check if URL should be crawled based on domain filtering rules.

        Thread-Safety: SAFE
        - Pure function using only local variables and immutable config
        - No shared state modified

        Filtering Rules:
        1. Same domain check (if enabled)
        2. Allowed paths check (if specified)
        3. Blocked patterns check (if specified)

        Returns:
            True if URL should be crawled, False otherwise
        """
        try:
            parsed = urllib.parse.urlparse(url)
            url_domain = parsed.netloc.lower()

            # =================================================================
            # SAME DOMAIN CHECK
            # =================================================================
            if self.same_domain_only:
                if self.include_subdomains:
                    # Allow exact match OR subdomain of base domain
                    # e.g., origin=www.example.com allows api.example.com
                    if not (url_domain == self._origin_domain or
                            url_domain.endswith('.' + self._base_domain) or
                            url_domain == self._base_domain):
                        return False
                else:
                    # Strict: only exact domain match
                    if url_domain != self._origin_domain:
                        return False

            # =================================================================
            # ALLOWED PATHS CHECK
            # =================================================================
            if self.allowed_paths:
                path_lower = parsed.path.lower()
                if not any(path_lower.startswith(p.lower()) for p in self.allowed_paths):
                    return False

            # =================================================================
            # BLOCKED PATTERNS CHECK
            # =================================================================
            if self.blocked_patterns:
                url_lower = url.lower()
                if any(pattern.lower() in url_lower for pattern in self.blocked_patterns):
                    return False

            # =================================================================
            # ROBOTS.TXT CHECK
            # =================================================================
            # Only checking same domain's robots.txt roughly or all?
            # To be safe and compliant, we fetch it per domain.
            with self._robot_parsers_lock:
                if url_domain not in self._robot_parsers:
                    rp = urllib.robotparser.RobotFileParser()
                    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
                    rp.set_url(robots_url)
                    try:
                        # Allow max 1-2 sec to read robots.txt to avoid blocking too long
                        # We use a custom opener here or just read()
                        # read() might be synchronous and slow, so we set a timeout if possible, 
                        # but RobotFileParser.read() uses urllib.request.urlopen without timeout.
                        # It's better to fetch manually with timeout and parse.
                        req = urllib.request.Request(robots_url, headers={'User-Agent': '*'})
                        with urllib.request.urlopen(req, timeout=3, context=self._ssl_permissive) as response:
                            rp.parse(response.read().decode("utf-8").splitlines())
                    except Exception:
                        # If we can't get robots.txt, assume it's allowed
                        pass
                    self._robot_parsers[url_domain] = rp

            if not self._robot_parsers[url_domain].can_fetch("*", url):
                self._log(f"Robots.txt blocked access to {url}")
                return False

            return True

        except Exception:
            # On error, reject the URL to be safe
            return False

    # =========================================================================
    # SECTION 2.5: Rate Limiting
    # =========================================================================

    def _rate_limit(self):
        """
        Enforce hit_rate limit using time-based throttling.

        Thread-Safety: SAFE
        - Only called from run() (single thread)
        - _last_request_time is thread-local to crawler

        Back-Pressure: This prevents overwhelming target servers
        """
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            if elapsed < self._request_interval:
                sleep_time = self._request_interval - elapsed
                time.sleep(sleep_time)
        self._last_request_time = time.time()

    # =========================================================================
    # SECTION 2.6: HTTP Fetching with SSL Fallback
    # =========================================================================

    def _fetch_url(self, url: str) -> Tuple[Optional[bytes], int]:
        """
        Fetch URL content with SSL fallback.

        Thread-Safety: SAFE
        - Creates new Request object for each call
        - SSL contexts are read-only after init
        - No shared mutable state accessed

        Returns:
            Tuple of (content_bytes, status_code)
            On error: (None, error_code)
        """
        request = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'GoogleInADay/1.0 (ITU Educational Project)',
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'en-US,en;q=0.9,tr;q=0.8',
            }
        )

        # Try secure context first
        try:
            with urllib.request.urlopen(
                request,
                context=self._ssl_secure,
                timeout=10
            ) as response:
                return response.read(), response.getcode()
        except ssl.SSLError:
            # Fallback to permissive context
            try:
                with urllib.request.urlopen(
                    request,
                    context=self._ssl_permissive,
                    timeout=10
                ) as response:
                    self._log(f"SSL fallback used for: {url}")
                    return response.read(), response.getcode()
            except Exception as e:
                self._log(f"Fetch failed (SSL fallback): {url} - {e}")
                return None, 0
        except urllib.error.HTTPError as e:
            self._log(f"HTTP error {e.code}: {url}")
            return None, e.code
        except urllib.error.URLError as e:
            self._log(f"URL error: {url} - {e.reason}")
            return None, 0
        except Exception as e:
            self._log(f"Fetch failed: {url} - {e}")
            return None, 0

    # =========================================================================
    # SECTION 2.7: Content Parsing and Word Extraction
    # =========================================================================

    def _parse_content(self, url: str, content: bytes) -> Tuple[List[str], Counter]:
        """
        Parse HTML content and extract links + word frequencies.

        Thread-Safety: SAFE
        - Creates new parser instance for each call
        - All variables are local
        - No shared state accessed

        Returns:
            Tuple of (list_of_links, word_frequency_counter)
        """
        # Decode content with fallback
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text = content.decode('latin-1')
            except Exception:
                text = content.decode('utf-8', errors='ignore')

        # Parse HTML
        parser = CrawlerHTMLParser(url)
        try:
            parser.feed(text)
        except Exception as e:
            self._log(f"Parse error for {url}: {e}")
            return [], Counter()

        # Extract words (2+ Unicode word characters)
        page_text = parser.get_text()
        words = re.findall(r'\b\w{2,}\b', page_text.lower(), re.UNICODE)
        word_counts = Counter(words)

        # Diagnostic logging
        self._log(f"Extracted {len(words)} total words, {len(word_counts)} unique from {url}")

        # Get links
        links = parser.get_links()

        return links, word_counts

    # =========================================================================
    # SECTION 2.8: Index Storage (Letter-Based Files)
    # =========================================================================

    @classmethod
    def _get_index_lock(cls, letter: str) -> threading.Lock:
        """
        Get or create lock for specific index file.

        Thread-Safety: SAFE
        - Uses class-level lock to protect _index_locks dict
        - Returns per-letter lock for fine-grained synchronization

        This prevents multiple crawlers from corrupting the same
        index file while allowing parallel writes to different letters.
        """
        with cls._index_locks_lock:
            if letter not in cls._index_locks:
                cls._index_locks[letter] = threading.Lock()
            return cls._index_locks[letter]

    def _index_words(self, url: str, word_counts: Counter, depth: int):
        """
        Index words to letter-based storage files.

        Thread-Safety: SAFE
        - Uses per-letter locks for file access
        - Atomic file operations (append mode)
        - Format: {word} {url} {origin} {depth} {frequency}

        File Organization:
        - data/storage/a.data - words starting with 'a'
        - data/storage/b.data - words starting with 'b'
        - ...
        - data/storage/0.data - words starting with digits/special
        """
        if not word_counts:
            self._log(f"No words extracted from {url} - skipping index")
            return

        self._log(f"Indexing {len(word_counts)} unique words from {url}")

        # Group words by first letter
        words_by_letter: Dict[str, List[Tuple[str, int]]] = {}
        for word, freq in word_counts.items():
            first_char = word[0].lower()
            if first_char.isalpha():
                letter = first_char
            else:
                letter = '0'  # Non-alphabetic

            if letter not in words_by_letter:
                words_by_letter[letter] = []
            words_by_letter[letter].append((word, freq))

        # Write to each letter file with appropriate lock
        for letter, words in words_by_letter.items():
            lock = self._get_index_lock(letter)
            filepath = os.path.join(self.STORAGE_DIR, f"{letter}.data")

            # Build content for this letter
            lines = []
            for word, freq in words:
                # Format: word url origin depth frequency
                line = f"{word} {url} {self.origin} {depth} {freq}"
                lines.append(line)

            # ================================================================
            # CRITICAL SECTION: File Write
            # ================================================================
            # Thread-Safety: Lock ensures only one thread writes at a time
            # Append mode allows concurrent readers (if any)
            # ================================================================
            with lock:
                try:
                    with open(filepath, 'a', encoding='utf-8') as f:
                        f.write('\n'.join(lines) + '\n')
                except Exception as e:
                    self._log(f"Index write error ({letter}.data): {e}")

    # =========================================================================
    # SECTION 2.9: State Persistence
    # =========================================================================

    def _save_state(self):
        """
        Save crawler state to files for resume capability.

        Thread-Safety: SAFE
        - Uses _lock when reading shared state
        - Atomic file write (temp + replace)

        Files saved:
        - {id}.data: JSON status and configuration
        - {id}.queue: Current URL queue
        """
        # Gather state under lock
        with self._lock:
            state = {
                "crawler_id": self.crawler_id,
                "origin": self.origin,
                "status": self.status,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "config": {
                    "max_depth": self.max_depth,
                    "hit_rate": self.hit_rate,
                    "max_queue_capacity": self.max_queue_capacity,
                    "max_urls_to_visit": self.max_urls_to_visit
                },
                "stats": {
                    "urls_crawled": self.urls_crawled,
                    "urls_failed": self.urls_failed,
                    "urls_queued": self.url_queue.qsize(),
                    "urls_visited": len(self.visited_urls)
                }
            }
            visited_copy = set(self.visited_urls)

        # Save status file (atomic write)
        status_path = os.path.join(self.CRAWLERS_DIR, f"{self.crawler_id}.data")
        self._atomic_write(status_path, json.dumps(state, indent=2))

        # Save queue snapshot
        queue_path = os.path.join(self.CRAWLERS_DIR, f"{self.crawler_id}.queue")
        queue_items = []

        # Drain queue to list (non-destructive snapshot via copy)
        temp_queue = []
        while True:
            try:
                item = self.url_queue.get_nowait()
                temp_queue.append(item)
                queue_items.append(f"{item[0]} {item[1]}")
            except queue.Empty:
                break

        # Restore queue
        for item in temp_queue:
            try:
                self.url_queue.put_nowait(item)
            except queue.Full:
                break

        self._atomic_write(queue_path, '\n'.join(queue_items))

        # Save visited URLs
        visited_lines = [
            f"{url} {self.crawler_id} {datetime.now().isoformat()}"
            for url in visited_copy
        ]

        # Append to global visited file with lock
        visited_lock = self._get_index_lock('_visited')
        with visited_lock:
            try:
                with open(self.VISITED_FILE, 'a', encoding='utf-8') as f:
                    if visited_lines:
                        f.write('\n'.join(visited_lines) + '\n')
            except Exception as e:
                self._log(f"Failed to save visited URLs: {e}")

    def _atomic_write(self, filepath: str, content: str):
        """
        Write file atomically to prevent corruption.

        Thread-Safety: SAFE
        - Writes to temp file first
        - os.replace() is atomic on most systems
        """
        temp_path = filepath + ".tmp"
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(temp_path, filepath)
        except Exception as e:
            self._log(f"Atomic write failed: {filepath} - {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def _load_state(self):
        """
        Load state from files when resuming.

        Thread-Safety: SAFE
        - Called during init/run before concurrent access
        - Modifies only local instance state
        """
        # Load visited URLs from global file
        if os.path.exists(self.VISITED_FILE):
            try:
                with open(self.VISITED_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        parts = line.strip().split(' ')
                        if len(parts) >= 1:
                            self.visited_urls.add(parts[0])
            except Exception as e:
                self._log(f"Failed to load visited URLs: {e}")

        # Load queue
        queue_path = os.path.join(self.CRAWLERS_DIR, f"{self.crawler_id}.queue")
        if os.path.exists(queue_path):
            try:
                with open(queue_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        parts = line.strip().split(' ')
                        if len(parts) >= 2:
                            url = parts[0]
                            depth = int(parts[1])
                            if url not in self.visited_urls:
                                try:
                                    self.url_queue.put_nowait((url, depth))
                                except queue.Full:
                                    break
            except Exception as e:
                self._log(f"Failed to load queue: {e}")

    # =========================================================================
    # SECTION 2.10: Logging
    # =========================================================================

    def _log(self, message: str):
        """
        Log message to buffer and file.

        Thread-Safety: SAFE
        - Uses separate lock for log buffer
        - Append mode for file writes
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"

        # Add to in-memory buffer
        with self._log_buffer_lock:
            self._log_buffer.append(log_entry)
            # Keep last 100 entries
            if len(self._log_buffer) > 100:
                self._log_buffer = self._log_buffer[-100:]

        # Write to log file
        log_path = os.path.join(self.CRAWLERS_DIR, f"{self.crawler_id}.logs")
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
        except Exception:
            pass  # Logging should not crash crawler

        # Also log to console
        logger.info(f"[{self.crawler_id}] {message}")

    def get_logs(self, limit: int = 50) -> List[str]:
        """
        Get recent log entries.

        Thread-Safety: SAFE
        - Lock protects buffer read
        """
        with self._log_buffer_lock:
            return self._log_buffer[-limit:]

    def get_status(self) -> dict:
        """
        Get current crawler status.

        Thread-Safety: SAFE
        - Lock protects shared state read
        """
        with self._lock:
            return {
                "crawler_id": self.crawler_id,
                "origin": self.origin,
                "status": self.status,
                "config": {
                    "max_depth": self.max_depth,
                    "hit_rate": self.hit_rate,
                    "max_queue_capacity": self.max_queue_capacity,
                    "max_urls_to_visit": self.max_urls_to_visit,
                    "same_domain_only": self.same_domain_only,
                    "include_subdomains": self.include_subdomains,
                    "allowed_paths": self.allowed_paths,
                    "blocked_patterns": self.blocked_patterns
                },
                "stats": {
                    "urls_crawled": self.urls_crawled,
                    "urls_failed": self.urls_failed,
                    "urls_queued": self.url_queue.qsize(),
                    "urls_visited": len(self.visited_urls)
                },
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at
            }

    # =========================================================================
    # SECTION 2.11: Main Execution Loop
    # =========================================================================

    def run(self):
        """
        Main crawler execution loop.

        Thread-Safety: This is THE crawler thread
        =========================================
        This method runs in its own thread. Key synchronization points:

        1. PAUSE CHECK (blocking):
           self._pause_event.wait()
           - Blocks if clear, proceeds if set
           - Other threads can call pause()/resume()

        2. STOP CHECK (non-blocking):
           self._stop_event.is_set()
           - Returns immediately
           - Checked at loop start and after pause

        3. QUEUE ACCESS (blocking with timeout):
           self.url_queue.get(timeout=1.0)
           - 1 second timeout allows periodic stop checks
           - queue.Empty means natural completion

        4. SHARED STATE ACCESS:
           All access to visited_urls, stats protected by _lock

        Flow:
        1. Load state (if resuming)
        2. Seed queue with origin URL
        3. Loop until stopped or finished:
           a. Wait if paused
           b. Check stop signal
           c. Get URL from queue (with timeout)
           d. Skip if already visited or too deep
           e. Rate limit
           f. Fetch and parse URL
           g. Index words
           h. Add new links to queue
        4. Save final state
        """
        self._log("Crawler starting...")

        with self._lock:
            self.status = "Active"
            self.started_at = datetime.now().isoformat()

        # Load state if resuming
        if self.resume_from_files:
            self._log("Resuming from saved state...")
            self._load_state()

        # Seed queue with origin if empty
        if self.url_queue.empty():
            self.url_queue.put((self.origin, 0))
            self._log(f"Seeded queue with: {self.origin}")

        # =====================================================================
        # MAIN CRAWL LOOP
        # =====================================================================
        while not self._stop_event.is_set():
            # =================================================================
            # PAUSE CHECK: Block here if paused
            # =================================================================
            # Thread-Safety: .wait() is thread-safe
            # If _pause_event is clear, we block until set
            # Another thread can call resume() to unblock us
            # =================================================================
            self._pause_event.wait()

            # =================================================================
            # STOP CHECK: After unpausing, verify we should continue
            # =================================================================
            if self._stop_event.is_set():
                break

            # =================================================================
            # QUEUE ACCESS: Get next URL with timeout
            # =================================================================
            # Thread-Safety: queue.Queue.get() is atomic
            # Timeout allows periodic stop signal checks
            # =================================================================
            try:
                url, depth = self.url_queue.get(timeout=1.0)
            except queue.Empty:
                # Queue exhausted - natural completion
                self._log("Queue empty - crawl finished")
                break

            # =================================================================
            # DEPTH CHECK: Skip URLs beyond max_depth
            # =================================================================
            if depth > self.max_depth:
                continue

            # =================================================================
            # DEDUPLICATION CHECK
            # =================================================================
            # Thread-Safety: Lock protects visited_urls
            # =================================================================
            normalized_url = self._normalize_url(url)
            with self._lock:
                if normalized_url in self.visited_urls:
                    continue
                self.visited_urls.add(normalized_url)

            # =================================================================
            # RATE LIMITING
            # =================================================================
            self._rate_limit()

            # =================================================================
            # FETCH URL
            # =================================================================
            content, status_code = self._fetch_url(normalized_url)

            if content is None:
                with self._lock:
                    self.urls_failed += 1
                continue

            self._log(f"Crawled: {normalized_url} ({status_code})")

            # =================================================================
            # PARSE CONTENT
            # =================================================================
            links, word_counts = self._parse_content(normalized_url, content)

            # =================================================================
            # INDEX WORDS
            # =================================================================
            # Thread-Safety: _index_words uses per-letter locks
            # =================================================================
            self._index_words(normalized_url, word_counts, depth)

            # =================================================================
            # UPDATE STATS
            # =================================================================
            with self._lock:
                self.urls_crawled += 1
                current_count = self.urls_crawled

            # =================================================================
            # URL LIMIT CHECK
            # =================================================================
            if current_count >= self.max_urls_to_visit:
                self._log(f"URL limit reached: {self.max_urls_to_visit}")
                break

            # =================================================================
            # QUEUE CAPACITY 100% (AUTO-STOP) CHECK
            # =================================================================
            if self.url_queue.qsize() >= self.max_queue_capacity:
                self._log(f"Queue capacity 100% reached ({self.max_queue_capacity}). Auto-stopping crawler.")
                break

            # =================================================================
            # ADD DISCOVERED LINKS TO QUEUE
            # =================================================================
            # Thread-Safety: queue.put() is atomic
            # Back-Pressure: timeout prevents blocking forever if full
            # Domain Filtering: Only add URLs that pass filter rules
            # =================================================================
            for link in links:
                normalized_link = self._normalize_url(link)

                # Apply domain filtering
                if not self._should_crawl_url(normalized_link):
                    continue

                with self._lock:
                    if normalized_link in self.visited_urls:
                        continue

                try:
                    self.url_queue.put(
                        (normalized_link, depth + 1),
                        timeout=0.1  # Short timeout, skip if full
                    )
                    # Also check if exactly full after putting
                    if self.url_queue.qsize() >= self.max_queue_capacity:
                        self._log(f"Queue capacity 100% reached ({self.max_queue_capacity}). Auto-stopping crawler.")
                        self._stop_event.set()
                        break
                except queue.Full:
                    # Back-pressure: queue is full, stop crawling as requested
                    self._log(f"Queue capacity 100% reached ({self.max_queue_capacity}). Auto-stopping crawler.")
                    self._stop_event.set()
                    break

            # Periodic state save (every 50 URLs)
            if current_count % 50 == 0:
                self._save_state()

        # =====================================================================
        # CLEANUP: Save final state
        # =====================================================================
        with self._lock:
            if self._stop_event.is_set():
                self.status = "Stopped"
            else:
                self.status = "Finished"
            self.finished_at = datetime.now().isoformat()

        self._save_state()
        self._log(f"Crawler finished. Status: {self.status}, URLs crawled: {self.urls_crawled}")


# =============================================================================
# SECTION 3: Convenience Functions
# =============================================================================

def create_crawler(
    origin: str,
    max_depth: int = 3,
    hit_rate: float = 100.0,
    max_queue_capacity: int = 10000,
    max_urls_to_visit: int = 1000,
    same_domain_only: bool = True,
    include_subdomains: bool = False,
    allowed_paths: Optional[List[str]] = None,
    blocked_patterns: Optional[List[str]] = None
) -> CrawlerJob:
    """
    Factory function to create and start a new crawler.

    Thread-Safety: SAFE
    - Creates new CrawlerJob instance
    - Starts thread after initialization

    Returns:
        Started CrawlerJob instance
    """
    crawler_id = f"{int(time.time())}_{threading.current_thread().ident}"

    crawler = CrawlerJob(
        crawler_id=crawler_id,
        origin=origin,
        max_depth=max_depth,
        hit_rate=hit_rate,
        max_queue_capacity=max_queue_capacity,
        max_urls_to_visit=max_urls_to_visit,
        same_domain_only=same_domain_only,
        include_subdomains=include_subdomains,
        allowed_paths=allowed_paths,
        blocked_patterns=blocked_patterns
    )

    crawler.start()
    return crawler


# =============================================================================
# SECTION 4: Module Self-Test
# =============================================================================

if __name__ == "__main__":
    # Quick test
    print("CrawlerJob module loaded successfully.")
    print("Thread-safety mechanisms:")
    print("  - threading.Event: Pause/Stop signals")
    print("  - queue.Queue: Thread-safe URL frontier")
    print("  - threading.Lock: Shared state protection")
    print("  - Atomic writes: File persistence")
