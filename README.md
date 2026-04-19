# Quiz HW2 - Build Google with Multi-Agent AI

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)](#run-on-localhost)
[![Flask](https://img.shields.io/badge/Flask-API-000000?style=for-the-badge&logo=flask&logoColor=white)](#api-contracts-hw2)
[![Search](https://img.shields.io/badge/Search-Triples%20Enabled-34A853?style=for-the-badge)](#2-search)
[![Workflow](https://img.shields.io/badge/Multi--Agent-Documented-EA4335?style=for-the-badge)](#multi-agent-workflow-requirement)

Localhost mini search system for ITU AI Aided Computer Engineering HW2.

Project 1 crawler/search spirit is preserved, but HW2 delivery is developed and documented with a Multi-Agent workflow.

## Quick Links

- [Scope](#scope)
- [API Contracts](#api-contracts-hw2)
- [Run on Localhost](#run-on-localhost)
- [Testing](#testing)
- [Deliverables](#deliverables)

## Scope

- Native-only core logic for crawling, indexing, and searching
- Single-machine, large-scale friendly design
- Back-pressure support (queue depth + rate limit)
- Search while indexing is active (Hybrid model)
- Simple UI dashboard for indexing, search, and system state
- Multi-agent collaboration evidence via workflow and agent description files

<details>
<summary><strong>HW2 Checklist</strong></summary>

- [x] Native crawler/index/search core
- [x] `POST /index` contract (`origin`, `k`)
- [x] `GET /search` triple output: `[relevant_url, origin_url, depth]`
- [x] Search while indexing
- [x] Multi-agent workflow documentation
- [x] Per-agent description files

</details>

## Technology Constraints

Core implementation uses language-native modules for exercise logic:

- `urllib.request`, `urllib.parse`, `urllib.error`, `urllib.robotparser`
- `threading`, `queue`
- `html.parser`
- `json`, `os`, `time`, `re`, `collections`

Allowed external runtime libraries:

- `flask`
- `flask-cors`

## Architecture Summary

Hybrid indexing/search design:

1. Active working set in memory for low-latency reads
2. Periodic disk snapshots for durability and resume support
3. Letter-partitioned index files (`a.data` ... `z.data`, `0.data`)
4. Thread-safe write paths with per-partition locks

High-level components:

- `app.py`: Flask API and dashboard routes
- `services/crawler_service.py`: crawler lifecycle orchestration
- `utils/crawler_job.py`: threaded crawler, queue/back-pressure, snapshotting
- `services/search_service.py`: relevance scoring and result shaping
- `demo/*.html`: crawler/status/search UI

## API Contracts (HW2)

### 1. Index

`POST /index`

Request body:

```json
{
  "origin": "https://example.com",
  "k": 3,
  "hit_rate": 50,
  "max_queue_capacity": 10000,
  "max_urls_to_visit": 2000
}
```

Response:

```json
{
  "crawler_id": "example.com",
  "origin": "https://example.com",
  "k": 3,
  "status": "Active"
}
```

### 2. Search

`GET /search?query=python&pageLimit=10&pageOffset=0&sortBy=relevance`

Response includes required triple list and backward-compatible rich results:

```json
{
  "query": "python",
  "triples": [
    ["https://docs.python.org/tutorial", "https://python.org", 1]
  ],
  "results": [
    {
      "relevant_url": "https://docs.python.org/tutorial",
      "origin_url": "https://python.org",
      "depth": 1,
      "score": 8.45
    }
  ],
  "total_results": 1
}
```

### 3. Dashboard Endpoints

- `GET /crawler/status/<crawler_id>`
- `GET /crawler/stats`
- `GET /index/stats`

UI routes:

- `GET /crawler`
- `GET /status`
- `GET /search-page`

## Run on Localhost

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start server:

```bash
python app.py
```

3. Open dashboard:

`http://localhost:3600/`

## Multi-Agent Workflow Requirement

Development process is documented in:

- `multi_agent_workflow.md`

Per-agent description files are provided in:

- `agents/lead_architect_agent.md`
- `agents/network_crawler_specialist.md`
- `agents/data_search_engineer.md`
- `agents/ui_integration_expert.md`
- `agents/qa_verificator_agent.md`

## Testing

Current tests:

```bash
python -m unittest discover -s utils/__test__ -v
```

Planned HW2 validation matrix includes:

- indexing while search is active
- back-pressure threshold behavior
- snapshot/recovery correctness
- triple contract compatibility

## Deliverables

- Working codebase
- `README.md`
- `product_prd.md`
- `recommendation.md`
- `multi_agent_workflow.md`
- Agent description files under `agents/`
