# Product Requirements Document
## Google in a Day - Mini Search Engine

| Field | Value |
|-------|-------|
| **Project Name** | Google in a Day |
| **Version** | 1.0 |
| **Course** | AI Aided Computer Engineering (ITU) |
| **Document Status** | Draft |
| **Created** | 2026-03-21 |
| **Reference** | [Gold Standard Repository](https://github.com/ereneld/crawler) |

---

## 1. Executive Summary

### 1.1 Vision
Build a fully functional mini search engine using only native Python libraries, demonstrating core concepts of web crawling, indexing, and information retrieval in an educational context.

### 1.2 Problem Statement
Understanding how search engines work internally is essential for computer engineering students. This project provides hands-on experience with:
- Multi-threaded web crawling
- Inverted index construction
- Relevance-based ranking algorithms
- RESTful API design
- Real-time dashboard development

### 1.3 Success Criteria (Gold Standard)
- [ ] Crawl and index 1,000+ pages from a seed URL
- [ ] Search latency < 100ms for indexed content
- [ ] Pause/Resume/Stop functionality with state persistence
- [ ] Real-time dashboard showing crawl progress
- [ ] 80%+ unit test coverage on critical modules
- [ ] Zero external crawler/parser dependencies

---

## 2. Technical Constraints

### 2.1 Allowed Libraries (Native Python)
```python
# Core Functionality
import urllib.request      # HTTP requests
import urllib.parse        # URL manipulation
import urllib.error        # Error handling
import urllib.robotparser  # robots.txt compliance (optional)

# Concurrency
import threading           # Thread management
import queue               # Thread-safe queues

# Parsing & Data
import html.parser         # HTML parsing (HTMLParser class)
import json                # Data serialization
import re                  # Regular expressions

# System & Utilities
import os                  # File operations
import time                # Timing and delays
import logging             # Logging
import hashlib             # URL hashing (optional)
import collections         # Counter, defaultdict

# Testing
import unittest            # Unit testing framework
```

### 2.2 Allowed External Libraries (Minimal)
```python
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
```

### 2.3 Forbidden Libraries
- `requests`, `httpx`, `aiohttp` (use `urllib` instead)
- `BeautifulSoup`, `lxml`, `scrapy` (use `html.parser` instead)
- `celery`, `asyncio` (use `threading` instead)
- Any other web scraping or parsing frameworks

---

## 3. System Architecture

### 3.1 Directory Structure
```
project-google/
├── app.py                        # Flask API server (port 3600)
├── requirements.txt              # flask, flask-cors
├── product_prd.md                # This document
│
├── services/
│   ├── __init__.py
│   ├── crawler_service.py        # Crawler lifecycle management
│   └── search_service.py         # Search and ranking logic
│
├── utils/
│   ├── __init__.py
│   ├── crawler_job.py            # CrawlerJob(threading.Thread)
│   ├── html_parser.py            # Custom HTMLParser subclass
│   └── __test__/
│       ├── __init__.py
│       ├── test_html_parser.py   # HTML parser unit tests
│       ├── test_crawler_job.py   # Crawler unit tests
│       └── test_search.py        # Search unit tests
│
├── demo/                         # Frontend dashboard
│   ├── crawler.html              # Crawler control page
│   ├── status.html               # Status monitoring page
│   └── search.html               # Search interface
│
└── data/                         # Auto-created at runtime
    ├── storage/                  # Word index files
    │   ├── a.data
    │   ├── b.data
    │   └── ... (a-z, 0-9)
    ├── crawlers/                 # Crawler state files
    │   ├── {crawler_id}.data     # Status JSON
    │   ├── {crawler_id}.logs     # Log entries
    │   └── {crawler_id}.queue    # URL queue backup
    └── visited_urls.data         # Global visited URL set
```

### 3.2 Component Diagram
```
┌─────────────────────────────────────────────────────────────────┐
│                         Flask REST API                          │
│                          (app.py:3600)                          │
├──────────────────┬──────────────────┬───────────────────────────┤
│   /crawler/*     │    /search       │      Static Files         │
│   endpoints      │    endpoint      │      (/demo/*)            │
└────────┬─────────┴────────┬─────────┴───────────────────────────┘
         │                  │
         ▼                  ▼
┌─────────────────┐  ┌─────────────────┐
│ CrawlerService  │  │  SearchService  │
│ - create()      │  │  - search()     │
│ - pause()       │  │  - rank()       │
│ - resume()      │  │  - paginate()   │
│ - stop()        │  │                 │
│ - status()      │  │                 │
└────────┬────────┘  └────────┬────────┘
         │                    │
         ▼                    │
┌─────────────────┐           │
│   CrawlerJob    │           │
│ (Thread Pool)   │           │
│ - _pause_event  │           │
│ - _stop_event   │           │
│ - url_queue     │           │
└────────┬────────┘           │
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────┐
│           File-Based Persistence        │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │ storage/*.data│  │ crawlers/*.data │   │
│  │ (word index) │  │ (crawler state)│   │
│  └─────────────┘  └─────────────────┘   │
└─────────────────────────────────────────┘
```

---

## 4. Functional Requirements

### 4.1 CrawlerJob Class Specification

#### 4.1.1 Class Interface
```python
class CrawlerJob(threading.Thread):
    """
    Multi-threaded web crawler with pause/resume/stop capability.

    Thread-safety is achieved through:
    - threading.Event for pause/stop signals
    - queue.Queue for URL frontier (built-in thread-safe)
    - Atomic file operations for persistence
    """

    def __init__(
        self,
        crawler_id: str,              # Unique identifier
        origin: str,                  # Seed URL
        max_depth: int,               # Maximum crawl depth (1-1000)
        hit_rate: float = 100.0,      # Requests per second (0.1-1000)
        max_queue_capacity: int = 10000,  # Back-pressure limit
        max_urls_to_visit: int = 1000,    # Session URL limit
        resume_from_files: bool = False   # Resume from saved state
    ):
        super().__init__(daemon=True)

        # Thread control events
        self._pause_event = threading.Event()
        self._stop_event = threading.Event()
        self._pause_event.set()  # Start in running state

        # Thread-safe URL queue with back-pressure
        self.url_queue = queue.Queue(maxsize=max_queue_capacity)

        # State tracking
        self.visited_urls: set = set()
        self.urls_crawled: int = 0
        self.status: str = "Initialized"

    def run(self) -> None:
        """Main crawl loop - dequeues and processes URLs."""
        pass

    def pause(self) -> None:
        """Pause crawling - thread blocks on _pause_event.wait()."""
        self._pause_event.clear()
        self.status = "Paused"

    def resume(self) -> None:
        """Resume crawling - unblock waiting thread."""
        self._pause_event.set()
        self.status = "Active"

    def stop(self) -> None:
        """Stop crawling gracefully."""
        self._stop_event.set()
        self._pause_event.set()  # Unblock if paused
        self.status = "Stopped"

    def is_paused(self) -> bool:
        """Check if crawler is paused."""
        return not self._pause_event.is_set()
```

#### 4.1.2 Main Crawl Loop Pattern
```python
def run(self):
    """
    Main execution loop with pause/stop support.
    """
    self.status = "Active"
    self._load_visited_urls()
    self.url_queue.put((self.origin, 0))

    while not self._stop_event.is_set():
        # PAUSE CHECK: Block here if paused
        self._pause_event.wait()

        # EXIT CHECK: After unpausing, check if stopped
        if self._stop_event.is_set():
            break

        try:
            url, depth = self.url_queue.get(timeout=1.0)
        except queue.Empty:
            # Queue exhausted - natural completion
            break

        if depth > self.max_depth:
            continue

        if url in self.visited_urls:
            continue

        # Rate limiting
        self._rate_limit()

        # Crawl and extract
        try:
            content, links = self._crawl_url(url)
            self._index_content(url, content, depth)

            # Add discovered links
            for link in links:
                if link not in self.visited_urls:
                    try:
                        self.url_queue.put((link, depth + 1), timeout=1.0)
                    except queue.Full:
                        # Back-pressure: skip URL when queue is full
                        pass

            self.visited_urls.add(url)
            self.urls_crawled += 1

        except Exception as e:
            self._log_error(url, e)

        # Check URL limit
        if self.urls_crawled >= self.max_urls_to_visit:
            break

    # Final status
    self.status = "Finished" if not self._stop_event.is_set() else "Interrupted"
    self._save_state()
```

### 4.2 State Machine

#### 4.2.1 State Definitions
| State | Condition | Behavior |
|-------|-----------|----------|
| **Active** | `pause_event.is_set() and not stop_event.is_set()` | Crawling URLs normally |
| **Paused** | `not pause_event.is_set()` | Thread blocked on `wait()` |
| **Stopped** | `stop_event.is_set()` | Thread exits, state saved |
| **Finished** | Queue empty, no stop signal | Natural completion |

#### 4.2.2 State Transition Diagram
```
                     create()
                        │
                        ▼
               ┌─────────────────┐
               │   Initialized   │
               └────────┬────────┘
                        │ start()
                        ▼
               ┌─────────────────┐
        ┌──────│     Active      │◄─────┐
        │      └────────┬────────┘      │
        │               │               │
        │ pause()       │ stop()        │ resume()
        │               │               │
        ▼               │               │
┌─────────────────┐     │      ┌────────┴────────┐
│     Paused      │─────┼─────►│     Stopped     │
└─────────────────┘     │      └─────────────────┘
        │               │               ▲
        │ stop()        │               │
        └───────────────┴───────────────┘
                        │
                        │ (queue empty)
                        ▼
               ┌─────────────────┐
               │    Finished     │
               └─────────────────┘
```

### 4.3 Index Storage Format

#### 4.3.1 Letter-Based File Organization
Words are stored in files based on their first character:
- `a.data` - words starting with 'a'
- `b.data` - words starting with 'b'
- ...
- `z.data` - words starting with 'z'
- `0.data` - words starting with digits or special characters

#### 4.3.2 File Format Specification
```
# Format: {word} {found_url} {origin_url} {depth} {frequency}
# Delimiter: single space
# Sorted by: word (alphabetical), then frequency (descending)

python https://docs.python.org/tutorial https://python.org 1 23
python https://realpython.com/guide https://python.org 2 15
programming https://en.wikipedia.org/Programming https://python.org 2 8
```

#### 4.3.3 Index Entry Fields
| Field | Description | Example |
|-------|-------------|---------|
| `word` | Lowercase, sanitized keyword | `python` |
| `found_url` | URL where word was found | `https://docs.python.org/tutorial` |
| `origin_url` | Seed URL of the crawl | `https://python.org` |
| `depth` | Crawl depth from origin (0 = seed) | `1` |
| `frequency` | Word occurrence count in document | `23` |

### 4.4 REST API Specification

#### 4.4.1 Server Configuration
```python
HOST = "0.0.0.0"
PORT = 3600
CORS_ORIGINS = "*"  # Development setting
```

#### 4.4.2 Endpoints

##### Create Crawler
```http
POST /crawler/create
Content-Type: application/json

{
    "origin": "https://example.com",
    "max_depth": 3,
    "hit_rate": 100.0,
    "max_queue_capacity": 10000,
    "max_urls_to_visit": 1000
}

Response 201:
{
    "crawler_id": "1679404800_140234567890",
    "status": "Active"
}
```

##### Get Crawler Status
```http
GET /crawler/status/{crawler_id}

Response 200:
{
    "crawler_id": "1679404800_140234567890",
    "status": "Active",
    "origin": "https://example.com",
    "config": {
        "max_depth": 3,
        "hit_rate": 100.0,
        "max_queue_capacity": 10000,
        "max_urls_to_visit": 1000
    },
    "stats": {
        "urls_crawled": 150,
        "urls_queued": 342,
        "urls_failed": 3
    },
    "logs": [
        "[2026-03-21 14:30:01] Crawled: https://example.com (200 OK)",
        "[2026-03-21 14:30:02] Found 23 links"
    ]
}
```

##### Control Endpoints
```http
POST /crawler/pause/{crawler_id}
POST /crawler/resume/{crawler_id}
POST /crawler/stop/{crawler_id}
POST /crawler/resume-from-files/{crawler_id}

Response 200:
{
    "status": "Paused"  # or "Active", "Stopped"
}
```

##### List All Crawlers
```http
GET /crawler/list

Response 200:
[
    {
        "crawler_id": "1679404800_140234567890",
        "origin": "https://example.com",
        "status": "Active",
        "urls_crawled": 150
    },
    ...
]
```

##### Get Statistics
```http
GET /crawler/stats

Response 200:
{
    "total_crawlers": 3,
    "active_crawlers": 1,
    "total_urls_crawled": 2547,
    "total_words_indexed": 18234,
    "storage_size_bytes": 4521678
}
```

##### Clear All Data
```http
POST /crawler/clear

Response 200:
{
    "status": "success",
    "message": "All data cleared"
}
```

##### Search
```http
GET /search?query=python+programming&pageLimit=10&pageOffset=0&sortBy=relevance

Response 200:
{
    "query": "python programming",
    "query_words": ["python", "programming"],
    "results": [
        {
            "url": "https://docs.python.org/tutorial",
            "word": "python",
            "origin": "https://python.org",
            "depth": 1,
            "frequency": 23,
            "score": 8.45
        },
        ...
    ],
    "total_results": 156,
    "page_limit": 10,
    "page_offset": 0,
    "sort_by": "relevance",
    "files_searched": 2
}
```

##### Random Word (I'm Feeling Lucky)
```http
GET /search/random

Response 200:
{
    "word": "algorithm"
}
```

### 4.5 Search Ranking Algorithm

#### 4.5.1 Relevance Score Formula
```
Score(word, url) = frequency × depth_boost × match_quality

Where:
  depth_boost = 1 / (1 + depth × 0.1)
  match_quality = 1.0 (exact match)
```

#### 4.5.2 Sorting Options
| Sort By | Algorithm |
|---------|-----------|
| `relevance` | Score descending (default) |
| `frequency` | Frequency descending |
| `depth` | Depth ascending (closer to seed first) |

#### 4.5.3 Multi-Word Query Handling
For queries with multiple words:
1. Search each word in its respective letter file
2. Aggregate results by URL
3. Combine scores (sum or average)
4. Sort by combined score

---

## 5. Non-Functional Requirements

### 5.1 Thread-Safety Strategy

#### 5.1.1 Synchronization Mechanisms
| Resource | Mechanism | Rationale |
|----------|-----------|-----------|
| URL Queue | `queue.Queue(maxsize=N)` | Built-in thread-safe FIFO with blocking |
| Pause Signal | `threading.Event()` | `.wait()` blocks, `.set()` releases |
| Stop Signal | `threading.Event()` | Non-blocking check with `.is_set()` |
| Visited Set | Thread-local in single-crawler | Each crawler has own set |
| File I/O | Atomic write-temp-rename | Prevents partial writes |

#### 5.1.2 Event-Based Control Pattern
```python
# Correct pattern for pause/resume with stop check
while not self._stop_event.is_set():
    # Block here if paused
    self._pause_event.wait()

    # Re-check stop after unpausing
    if self._stop_event.is_set():
        break

    # ... do work ...
```

#### 5.1.3 Queue Operations with Timeout
```python
# Non-blocking put with timeout (back-pressure)
try:
    self.url_queue.put((url, depth), timeout=1.0)
except queue.Full:
    # Queue at capacity - skip this URL
    self._log("Queue full, skipping URL")

# Non-blocking get with timeout (graceful exit)
try:
    url, depth = self.url_queue.get(timeout=1.0)
except queue.Empty:
    # No more URLs - consider finishing
    break
```

### 5.2 Back-Pressure Strategy

#### 5.2.1 Configuration Parameters
| Parameter | Default | Min | Max | Purpose |
|-----------|---------|-----|-----|---------|
| `max_queue_capacity` | 10,000 | 100 | 100,000 | Memory protection |
| `max_urls_to_visit` | 1,000 | 0 | 10,000 | Session limit |
| `hit_rate` | 100.0 | 0.1 | 1,000.0 | Rate limiting (req/s) |

#### 5.2.2 Back-Pressure Mechanisms
1. **Queue Capacity Limit**: `queue.Queue(maxsize=N)` blocks/times out when full
2. **URL Visit Limit**: Stop crawling after N URLs processed
3. **Rate Limiting**: Sleep between requests based on `hit_rate`
4. **Depth Limiting**: Skip URLs beyond `max_depth`

#### 5.2.3 Rate Limiting Implementation
```python
def _rate_limit(self):
    """
    Enforce hit_rate limit using time-based throttling.
    """
    if self.last_request_time is not None:
        elapsed = time.time() - self.last_request_time
        required_interval = 1.0 / self.hit_rate
        if elapsed < required_interval:
            time.sleep(required_interval - elapsed)
    self.last_request_time = time.time()
```

### 5.3 Persistence for Resume

#### 5.3.1 File Types and Locations
| File | Path | Format | Purpose |
|------|------|--------|---------|
| Status | `data/crawlers/{id}.data` | JSON | Crawler configuration and stats |
| Logs | `data/crawlers/{id}.logs` | Text | Timestamped log entries |
| Queue | `data/crawlers/{id}.queue` | Text | URL and depth pairs |
| Visited | `data/visited_urls.data` | Text | Global visited URL set |
| Index | `data/storage/{letter}.data` | Text | Word index entries |

#### 5.3.2 Status File Format (.data)
```json
{
    "crawler_id": "1679404800_140234567890",
    "origin": "https://example.com",
    "status": "Paused",
    "created_at": "2026-03-21T14:00:00Z",
    "updated_at": "2026-03-21T14:30:00Z",
    "config": {
        "max_depth": 3,
        "hit_rate": 100.0,
        "max_queue_capacity": 10000,
        "max_urls_to_visit": 1000
    },
    "stats": {
        "urls_crawled": 150,
        "urls_failed": 3,
        "start_time": "2026-03-21T14:00:00Z"
    }
}
```

#### 5.3.3 Queue File Format (.queue)
```
# Format: {url} {depth}
https://example.com/page1 1
https://example.com/page2 1
https://example.com/subdir/page3 2
```

#### 5.3.4 Visited URLs Format
```
# Format: {url} {crawler_id} {timestamp}
https://example.com 1679404800_140234567890 2026-03-21T14:00:01Z
https://example.com/about 1679404800_140234567890 2026-03-21T14:00:02Z
```

#### 5.3.5 Atomic File Writing
```python
def _save_atomic(self, filepath: str, content: str):
    """
    Write file atomically to prevent corruption.
    """
    temp_path = filepath + ".tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(temp_path, filepath)  # Atomic operation
```

### 5.4 HTML Parsing

#### 5.4.1 Custom HTMLParser Implementation
```python
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

class CrawlerHTMLParser(HTMLParser):
    """
    Custom HTML parser for extracting links and text content.
    """

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list = []
        self.text_content: list = []
        self._in_script = False
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list):
        if tag == 'script':
            self._in_script = True
        elif tag == 'style':
            self._in_style = True
        elif tag == 'a':
            for attr, value in attrs:
                if attr == 'href' and value:
                    abs_url = urljoin(self.base_url, value)
                    if self._is_valid_url(abs_url):
                        self.links.append(abs_url)

    def handle_endtag(self, tag: str):
        if tag == 'script':
            self._in_script = False
        elif tag == 'style':
            self._in_style = False

    def handle_data(self, data: str):
        if not self._in_script and not self._in_style:
            text = data.strip()
            if text:
                self.text_content.append(text)

    def _is_valid_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https')

    def get_text(self) -> str:
        return ' '.join(self.text_content)

    def get_links(self) -> list:
        return list(set(self.links))  # Deduplicate
```

#### 5.4.2 URL Normalization Rules
1. Lowercase scheme and host
2. Remove default ports (80 for http, 443 for https)
3. Remove URL fragments (#anchor)
4. Remove trailing slashes (except for root)
5. Decode percent-encoded characters consistently

### 5.5 SSL/TLS Handling

#### 5.5.1 Dual Context Strategy
```python
import ssl
import urllib.request

def _setup_ssl_contexts(self):
    """
    Create two SSL contexts:
    - Secure: For properly configured sites
    - Permissive: Fallback for sites with certificate issues
    """
    # Secure context (default)
    self.ssl_secure = ssl.create_default_context()

    # Permissive context (fallback)
    self.ssl_permissive = ssl.create_default_context()
    self.ssl_permissive.check_hostname = False
    self.ssl_permissive.verify_mode = ssl.CERT_NONE
```

#### 5.5.2 Request with Fallback
```python
def _fetch_url(self, url: str) -> bytes:
    """
    Fetch URL with SSL fallback.
    """
    request = urllib.request.Request(
        url,
        headers={'User-Agent': 'GoogleInADay/1.0 (ITU Educational Project)'}
    )

    try:
        # Try secure first
        with urllib.request.urlopen(request, context=self.ssl_secure, timeout=10) as response:
            return response.read()
    except ssl.SSLError:
        # Fallback to permissive
        with urllib.request.urlopen(request, context=self.ssl_permissive, timeout=10) as response:
            return response.read()
```

---

## 6. Dashboard Specification

### 6.1 Pages

#### 6.1.1 Crawler Control Page (crawler.html)
- Seed URL input
- Configuration sliders (max_depth, hit_rate, max_urls)
- Start button
- Active crawlers list with status badges

#### 6.1.2 Status Monitoring Page (status.html)
- Real-time stats (URLs crawled, queued, failed)
- Progress bar
- Live log feed (auto-scroll)
- Pause/Resume/Stop buttons
- 2-second auto-refresh

#### 6.1.3 Search Page (search.html)
- Query input box
- "I'm Feeling Lucky" button
- Results list with:
  - URL (clickable)
  - Word highlighted
  - Depth indicator
  - Frequency badge
  - Relevance score
- Pagination controls
- Sort dropdown (relevance, frequency, depth)

### 6.2 UI Wireframe
```
┌────────────────────────────────────────────────────────────────┐
│  GOOGLE IN A DAY                    [Crawler] [Status] [Search] │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Seed URL: [https://example.com                      ]  │   │
│  │                                                          │   │
│  │  Max Depth: [====●====] 5    Hit Rate: [====●====] 100  │   │
│  │                                                          │   │
│  │  Queue Capacity: 10,000      URL Limit: 1,000           │   │
│  │                                                          │   │
│  │                        [START CRAWLER]                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Active Crawlers:                                               │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ ID: 1679404800  │ example.com │ ●Active │ 150 URLs     │    │
│  │ ID: 1679401200  │ python.org  │ ●Paused │ 523 URLs     │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

## 7. Testing Requirements

### 7.1 Test Coverage Targets
| Module | Target Coverage | Priority |
|--------|-----------------|----------|
| `html_parser.py` | 90% | P0 |
| `crawler_job.py` | 85% | P0 |
| `search_service.py` | 85% | P0 |
| `crawler_service.py` | 80% | P1 |

### 7.2 HTML Parser Test Cases
```python
class TestHTMLParser(unittest.TestCase):

    def test_extract_absolute_links(self):
        """Parser extracts absolute href URLs."""

    def test_convert_relative_links(self):
        """Parser converts relative URLs to absolute."""

    def test_extract_text_content(self):
        """Parser extracts visible text, ignoring tags."""

    def test_ignore_script_content(self):
        """Parser ignores JavaScript content."""

    def test_ignore_style_content(self):
        """Parser ignores CSS content."""

    def test_handle_malformed_html(self):
        """Parser handles unclosed tags gracefully."""

    def test_filter_non_http_links(self):
        """Parser filters mailto:, javascript:, etc."""

    def test_deduplicate_links(self):
        """Parser returns unique links only."""
```

### 7.3 Crawler Test Cases
```python
class TestCrawlerJob(unittest.TestCase):

    def test_thread_lifecycle(self):
        """Thread starts and can be stopped."""

    def test_pause_blocks_execution(self):
        """Pause event blocks the crawl loop."""

    def test_resume_continues_execution(self):
        """Resume event unblocks the crawl loop."""

    def test_stop_terminates_thread(self):
        """Stop event terminates the thread gracefully."""

    def test_url_deduplication(self):
        """Same URL is not visited twice."""

    def test_depth_limit_enforced(self):
        """URLs beyond max_depth are skipped."""

    def test_queue_capacity_limit(self):
        """Queue full condition handled gracefully."""

    def test_rate_limiting(self):
        """Requests respect hit_rate limit."""

    def test_state_persistence(self):
        """Queue and visited set saved on stop."""

    def test_resume_from_files(self):
        """Crawler resumes from saved state."""
```

### 7.4 Search Test Cases
```python
class TestSearch(unittest.TestCase):

    def test_single_word_search(self):
        """Single word returns matching entries."""

    def test_multi_word_search(self):
        """Multiple words searched across files."""

    def test_relevance_ranking(self):
        """Results sorted by relevance score."""

    def test_pagination(self):
        """Pagination returns correct slices."""

    def test_empty_query(self):
        """Empty query returns error."""

    def test_no_results(self):
        """Non-matching query returns empty list."""
```

---

## 8. Verification Plan

### 8.1 End-to-End Test Scenarios

#### Scenario 1: Basic Crawl
1. Start crawler with `https://example.com`, depth=2, limit=50
2. Verify status shows "Active"
3. Wait for completion or 30 URLs
4. Verify index files created in `data/storage/`
5. Search for a word from crawled content
6. Verify results match expectations

#### Scenario 2: Pause/Resume Cycle
1. Start crawler
2. After 10 URLs, call pause endpoint
3. Verify status is "Paused"
4. Call resume endpoint
5. Verify crawling continues
6. Verify URL count increases

#### Scenario 3: Stop and Resume from Files
1. Start crawler
2. After 20 URLs, call stop endpoint
3. Verify `.queue` and `.data` files saved
4. Call resume-from-files endpoint
5. Verify crawler continues from queue
6. Verify no duplicate URLs visited

#### Scenario 4: Dashboard Real-Time Updates
1. Open crawler.html, start a crawl
2. Open status.html for the crawler
3. Verify stats update every 2 seconds
4. Verify logs appear in real-time
5. Test pause/resume buttons

### 8.2 Performance Benchmarks
| Metric | Target | Test Method |
|--------|--------|-------------|
| Crawl throughput | 100 pages/min | Time 100 pages crawl |
| Search latency | < 100ms | Measure API response time |
| Memory usage | < 500 MB | Monitor process memory |
| File I/O | No corruption | Crash recovery test |

---

## 9. Appendices

### Appendix A: Error Codes
| Code | Description |
|------|-------------|
| 400 | Invalid request parameters |
| 404 | Crawler not found |
| 409 | Invalid state transition (e.g., pause already paused) |
| 500 | Internal server error |

### Appendix B: Glossary
| Term | Definition |
|------|------------|
| **Seed URL** | Starting point for the crawl |
| **Frontier** | Queue of URLs waiting to be crawled |
| **Inverted Index** | Data structure mapping words to documents |
| **Back-pressure** | Flow control preventing memory exhaustion |
| **TF-IDF** | Term Frequency-Inverse Document Frequency (ranking) |

### Appendix C: References
- [Gold Standard Repository](https://github.com/ereneld/crawler)
- [Python threading documentation](https://docs.python.org/3/library/threading.html)
- [Python queue documentation](https://docs.python.org/3/library/queue.html)
- [Flask documentation](https://flask.palletsprojects.com/)
