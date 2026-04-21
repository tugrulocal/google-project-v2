# Google in a Day
### Mini Search Engine with Native Python Threading

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-21%20passed-success)](utils/__test__)

A fully functional, educational search engine demonstrating core concepts of web crawling, inverted indexing, and relevance-based ranking—built entirely with native Python libraries (no Scrapy, BeautifulSoup, or external parsers)

**Course:** AI Aided Computer Engineering (İTÜ)
**Reference:** [Gold Standard Repository](https://github.com/ereneld/crawler)

---

## 📋 Table of Contents
- [Features](#-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Usage Guide](#-usage-guide)
- [API Reference](#-api-reference)
- [Testing](#-testing)
- [Technical Highlights](#-technical-highlights)
- [Project Structure](#-project-structure)
- [Deliverables](#-deliverables)

---

## ✨ Features

### Crawler
- ✅ **Multi-threaded Design:** Each crawler runs in its own thread (`threading.Thread`)
- ✅ **Pause/Resume/Stop:** Event-based control for crawler lifecycle
- ✅ **State Persistence:** Resume interrupted crawls from saved checkpoints
- ✅ **Back-Pressure Control:** Queue capacity limits prevent memory exhaustion
- ✅ **Rate Limiting:** Configurable requests per second (0.1 - 1000 req/s)
- ✅ **SSL Fallback:** Secure context first, permissive fallback for certificate issues
- ✅ **Depth-Bounded:** Configurable max crawl depth (1-1000)

### Indexing
- ✅ **Letter-Based Storage:** Words indexed in `a.data` through `z.data` files
- ✅ **Thread-Safe Writes:** Per-letter locks for concurrent crawler support
- ✅ **Frequency Tracking:** Word occurrence counts per URL
- ✅ **Depth Metadata:** Distance from seed URL stored for ranking

### Search & Ranking
- ✅ **Relevance Scoring:** `frequency × depth_boost × match_quality`
- ✅ **Multiple Sort Options:** Relevance, Frequency, or Depth
- ✅ **Pagination Support:** Configurable page size and offset
- ✅ **Multi-Word Queries:** Searches across multiple index files

### Dashboard
- ✅ **Real-Time Monitoring:** Auto-refresh status every 2 seconds
- ✅ **Live Logs:** Scrolling log feed with timestamps
- ✅ **Crawler Control:** Start, Pause, Resume, Stop buttons
- ✅ **Statistics Dashboard:** URLs crawled, queued, failed, indexed words
- ✅ **Search Interface:** Google-style search with "I'm Feeling Lucky"

---

## 🏗 Architecture

### Component Diagram
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

### Thread-Safety Mechanisms
| Resource | Protection | Pattern |
|----------|-----------|---------|
| URL Queue | `queue.Queue(maxsize=N)` | Built-in thread-safe FIFO |
| Pause Signal | `threading.Event()` | `.wait()` blocks, `.set()` releases |
| Stop Signal | `threading.Event()` | Non-blocking check with `.is_set()` |
| Visited URLs | `threading.Lock` | Mutual exclusion for set operations |
| Index Files | Per-letter `threading.Lock` | Fine-grained locking (a.data, b.data separate) |
| File I/O | Atomic write-temp-rename | `os.replace()` prevents partial writes |

### Back-Pressure Strategy
```python
# 1. Queue capacity limit enforces memory bounds
url_queue = queue.Queue(maxsize=10000)  # Default

# 2. Timeout-based put (non-blocking)
url_queue.put((url, depth), timeout=0.1)
# → queue.Full: Skip URL (back-pressure active)

# 3. Session URL limit
if urls_crawled >= max_urls_to_visit:
    break  # Stop crawling

# 4. Rate limiting
sleep(1.0 / hit_rate)  # Enforce requests/second
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Installation
```bash
# Clone repository
git clone https://github.com/yourusername/google-in-a-day.git
cd google-in-a-day

# Install dependencies
pip install -r requirements.txt
```

### Run Server
```bash
# Start Flask API on port 3600
python app.py
```

### Open Dashboard
```
http://localhost:3600/
```

---

## 📖 Usage Guide

### 1. Start a Crawler
**Via Dashboard:**
1. Navigate to `http://localhost:3600/crawler`
2. Enter seed URL (e.g., `https://example.com`)
3. Configure parameters:
   - **Max Depth:** How deep to crawl (1-1000)
   - **Hit Rate:** Requests per second (0.1-1000)
   - **Max URLs:** Session limit (1-10,000)
   - **Queue Capacity:** Memory limit (100-100,000)
4. Click **Start Crawler**

**Via API:**
```bash
curl -X POST http://localhost:3600/crawler/create \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "https://example.com",
    "max_depth": 3,
    "hit_rate": 100,
    "max_urls_to_visit": 1000
  }'
```

**Response:**
```json
{
  "crawler_id": "1679404800_12345",
  "status": "Active"
}
```

### 2. Monitor Crawler Status
**Via Dashboard:**
1. Navigate to `http://localhost:3600/status`
2. Select crawler from dropdown
3. View real-time statistics, logs, and progress

**Via API:**
```bash
curl http://localhost:3600/crawler/status/1679404800_12345
```

### 3. Control Crawler
**Pause:**
```bash
curl -X POST http://localhost:3600/crawler/pause/1679404800_12345
```

**Resume:**
```bash
curl -X POST http://localhost:3600/crawler/resume/1679404800_12345
```

**Stop:**
```bash
curl -X POST http://localhost:3600/crawler/stop/1679404800_12345
```

**Resume from Files (after stop):**
```bash
curl -X POST http://localhost:3600/crawler/resume-from-files/1679404800_12345
```

### 4. Search Indexed Content
**Via Dashboard:**
1. Navigate to `http://localhost:3600/search-page`
2. Enter query (e.g., `python programming`)
3. Select sort option (Relevance, Frequency, Depth)
4. Click **Search** or **I'm Feeling Lucky**

**Via API:**
```bash
curl "http://localhost:3600/search?query=python&pageLimit=10&pageOffset=0&sortBy=relevance"
```

**Response:**
```json
{
  "query": "python",
  "query_words": ["python"],
  "results": [
    {
      "word": "python",
      "url": "https://docs.python.org/tutorial",
      "origin": "https://python.org",
      "depth": 1,
      "frequency": 23,
      "score": 8.45
    }
  ],
  "total_results": 156,
  "page_limit": 10,
  "page_offset": 0
}
```

---

## 🔌 API Reference

### Crawler Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/crawler/create` | Start new crawler |
| GET | `/crawler/status/<id>` | Get crawler status |
| GET | `/crawler/list` | List all crawlers |
| POST | `/crawler/pause/<id>` | Pause active crawler |
| POST | `/crawler/resume/<id>` | Resume paused crawler |
| POST | `/crawler/stop/<id>` | Stop crawler |
| POST | `/crawler/resume-from-files/<id>` | Resume from saved state |
| POST | `/crawler/clear` | Clear all data |
| GET | `/crawler/stats` | Get aggregate statistics |

### Search Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/search` | Search indexed content |
| GET | `/search/random` | Get random word (I'm Feeling Lucky) |
| GET | `/index/stats` | Get index statistics |

### Search Query Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | Required | Search query |
| `pageLimit` | int | 10 | Results per page (1-100) |
| `pageOffset` | int | 0 | Results to skip |
| `sortBy` | string | relevance | Sort: `relevance`, `frequency`, `depth` |

---

## 🧪 Testing

### Run Unit Tests
```bash
# HTML Parser tests (21 tests)
python -m unittest utils.__test__.test_html_parser -v

# Crawler Job tests (20+ tests)
python -m unittest utils.__test__.test_crawler_job -v

# Run all tests
python -m unittest discover -s utils/__test__ -v
```

### Test Coverage
| Module | Tests | Coverage |
|--------|-------|----------|
| `html_parser.py` | 21 | 90%+ |
| `crawler_job.py` | 20+ | 85%+ |

### Manual Testing Checklist
- [ ] Start crawler with seed URL
- [ ] Verify URLs being crawled in logs
- [ ] Pause crawler, verify state freezes
- [ ] Resume crawler, verify continuation
- [ ] Stop crawler, verify graceful shutdown
- [ ] Resume from files, verify queue restored
- [ ] Search for indexed words
- [ ] Verify pagination works
- [ ] Test different sort options
- [ ] Clear all data, verify cleanup

---

## 🎯 Technical Highlights

### 1. Event-Based Thread Control
```python
class CrawlerJob(threading.Thread):
    def __init__(self):
        self._pause_event = threading.Event()  # .set() = running
        self._stop_event = threading.Event()   # .set() = stop

    def run(self):
        while not self._stop_event.is_set():
            self._pause_event.wait()  # BLOCKS if paused
            # ... crawl logic ...
```

**Why This Works:**
- `_pause_event.wait()`: Blocks thread until event is set (running state)
- `pause()`: Clears event → thread blocks on next iteration
- `resume()`: Sets event → thread unblocks and continues
- No busy-waiting, no polling, no CPU waste

### 2. Per-Letter Index Locking
```python
# Class-level lock dictionary
_index_locks: Dict[str, threading.Lock] = {}

@classmethod
def _get_index_lock(cls, letter: str) -> threading.Lock:
    with cls._index_locks_lock:
        if letter not in cls._index_locks:
            cls._index_locks[letter] = threading.Lock()
        return cls._index_locks[letter]

def _index_words(self, url: str, word_counts: Counter, depth: int):
    for word, freq in word_counts.items():
        letter = word[0].lower()
        lock = self._get_index_lock(letter)

        with lock:  # Only this letter file locked
            with open(f"{letter}.data", 'a') as f:
                f.write(f"{word} {url} {self.origin} {depth} {freq}\n")
```

**Benefits:**
- Multiple crawlers can write to different letters simultaneously
- Prevents file corruption from concurrent writes
- Better parallelism than single global lock

### 3. Atomic File Operations
```python
def _atomic_write(self, filepath: str, content: str):
    temp_path = filepath + ".tmp"
    with open(temp_path, 'w') as f:
        f.write(content)
    os.replace(temp_path, filepath)  # ATOMIC on most systems
```

**Prevents:**
- Partial writes on crash
- Reader seeing half-written data
- File corruption

---

## 📁 Project Structure

```
project-google/
├── app.py                          # Flask REST API (port 3600)
├── product_prd.md                  # Product Requirements Document
├── recommendation.md               # Production roadmap
├── README.md                       # This file
├── requirements.txt                # Dependencies (flask, flask-cors)
│
├── services/
│   ├── __init__.py
│   ├── crawler_service.py          # Crawler lifecycle management
│   └── search_service.py           # Search and ranking logic
│
├── utils/
│   ├── __init__.py
│   ├── crawler_job.py              # CrawlerJob(threading.Thread)
│   └── __test__/
│       ├── __init__.py
│       ├── test_html_parser.py     # HTML parser tests
│       └── test_crawler_job.py     # Crawler tests
│
├── demo/
│   ├── crawler.html                # Crawler control dashboard
│   ├── status.html                 # Real-time monitoring
│   └── search.html                 # Search interface
│
└── data/                           # Auto-created at runtime
    ├── storage/                    # Index files (a.data - z.data)
    ├── crawlers/                   # Crawler state ({id}.data, .logs, .queue)
    └── visited_urls.data           # Global visited URL set
```

---

## 📦 Deliverables (Final-4)

| Deliverable | Status | Path |
|-------------|--------|------|
| **Codebase** | ✅ Complete | Entire repository |
| **PRD** | ✅ Complete | `product_prd.md` |
| **README** | ✅ Complete | `README.md` |
| **Recommendation** | ✅ Complete | `recommendation.md` |

---

## 🎓 Educational Value

This project demonstrates:
- **Concurrency:** Threading, locks, events, queues
- **Web Technologies:** HTTP, HTML parsing, URL normalization
- **Data Structures:** Inverted index, FIFO queue, hash sets
- **File I/O:** Atomic writes, checkpointing, crash recovery
- **API Design:** RESTful endpoints, JSON responses
- **Frontend:** HTML/CSS/JS without frameworks

**AI Stewardship Questions to Prepare:**

1. **Why threading instead of multiprocessing?**
   - CPython GIL limits true parallelism, but threading is sufficient for I/O-bound crawling
   - `queue.Queue` is thread-safe but not process-safe
   - Lower memory overhead (shared memory vs. IPC)

2. **How is back-pressure implemented?**
   - `queue.Queue(maxsize=N)` blocks/times out when full
   - `put(timeout=0.1)` skips URLs if queue at capacity
   - `max_urls_to_visit` hard limit prevents infinite crawling

3. **What prevents race conditions?**
   - `threading.Lock` for `visited_urls` set
   - `threading.Event` for pause/stop signals (atomic)
   - Per-letter locks for index file writes
   - Atomic file operations (`os.replace()`)

---

## 📝 Notes

- **Port 3600** chosen to match Gold Standard repository
- **Only native Python** libraries used (no Scrapy, BeautifulSoup, requests)
- **Flask** is the only external dependency (allowed per course rules)
- **Thread-safety** prioritized throughout (locks, events, atomic operations)

---

## 📄 License

MIT License - Educational project for ITU AI Aided Computer Engineering course.

---

## 🙏 Acknowledgments

- **Gold Standard Repository:** [ereneld/crawler](https://github.com/ereneld/crawler)
- **Course Instructor:** ITU AI Aided Computer Engineering
- **Reference Materials:** Product PRD, course slides, technical specifications

---

**Built with ❤️ using only Python standard library + Flask**