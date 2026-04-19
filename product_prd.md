# Product Requirements Document
## Quiz HW2 - Build Google with Multi-Agent AI

| Field | Value |
|---|---|
| Project Name | Quiz HW2 - Build Google with Multi-Agent AI |
| Version | 2.0 |
| Course | ITU AI Aided Computer Engineering |
| Status | Active Draft |
| Date | 2026-04-19 |
| Architecture Decision | Hybrid (memory working set + disk snapshot) |

## 1. Goal

Build a crawler + search system similar to Project 1, but execute development through a documented Multi-Agent AI workflow.

The output must include both:

1. Functional system running on localhost
2. Clear evidence of multi-agent collaboration and decisions

## 2. Core Functional Requirements

### 2.1 Index

Given `origin` and `k`, start crawling and index discovered pages up to depth `k`.

Rules:

1. Never crawl the same normalized URL twice
2. Respect single-machine scalability constraints
3. Include back-pressure controls
4. Support controlled crawl lifecycle (start/pause/resume/stop)

Primary API contract:

- `POST /index`
- Request fields: `origin`, `k`
- Optional fields: `hit_rate`, `max_queue_capacity`, `max_urls_to_visit`, domain filters

### 2.2 Search

Given `query`, return relevant URLs.

Required output form:

- List of triples: `(relevant_url, origin_url, depth)`

Design requirement:

- Search should be callable while indexing remains active
- New results should appear incrementally as index grows

### 2.3 UI or CLI

Provide simple operator interface to:

1. Start indexing
2. Execute search
3. Monitor state:
   - indexing progress
   - queue depth
   - back-pressure status

This project uses dashboard UI (Flask static pages).

### 2.4 Resume (Plus)

Resume capability after interruption is a plus and is included in this project through saved state files.

## 3. Technical Constraints

### 3.1 Native-Only Core Logic

Must use native modules for crawler/search core behavior:

- `urllib.*`
- `threading`, `queue`
- `html.parser`
- file-based persistence with `os`, `json`

### 3.2 Minimal Runtime Dependencies

Allowed runtime libraries:

- `flask`
- `flask-cors`

### 3.3 Environment

- Localhost execution only
- Single machine design, no multi-node requirement

## 4. Hybrid Architecture Decision

### 4.1 Decision

Use Hybrid strategy:

1. Memory active working set for low search latency
2. Periodic disk snapshot for durability and restart safety

### 4.2 Why Hybrid

1. Faster incremental search visibility during active indexing
2. Better resilience than memory-only model
3. Better interactivity than disk-only model

### 4.3 Rejected Alternatives

1. Disk-first rejected for higher read latency during active indexing
2. Memory-first rejected for higher crash recovery risk

## 5. System Design

### 5.1 Crawler Pipeline

1. Seed origin enters queue at depth 0
2. Worker thread pops URL, normalizes, deduplicates
3. Fetches content via `urllib`
4. Extracts links/text using `HTMLParser`
5. Writes word postings to letter partitions
6. Enqueues discovered links with `depth + 1`

### 5.2 Back-Pressure

Two explicit controls:

1. Queue depth cap (`max_queue_capacity`)
2. Rate cap (`hit_rate` requests/sec)

Behavior under pressure:

1. Near-capacity -> throttle/discard new enqueue attempts
2. Hard cap reached -> controlled stop condition

### 5.3 Concurrency Model

1. Index writer path uses partition locks
2. Search reads can run while writer is active
3. Results are eventually consistent and incrementally visible

### 5.4 Persistence

1. Status snapshot (`.data`)
2. Frontier snapshot (`.queue`)
3. Logs (`.logs`)
4. Global visited record (`visited_urls.data`)

## 6. API Requirements

### 6.1 Index

`POST /index`

Response fields:

- `crawler_id`
- `origin`
- `k`
- `status`

### 6.2 Search

`GET /search?query=...`

Response requirements:

1. Must include `triples` list in HW2 form
2. May include extra metadata fields for UI (score, frequency, sort)

### 6.3 Status/Observability

1. `GET /crawler/status/<id>`
2. `GET /crawler/stats`
3. `GET /index/stats`

## 7. Multi-Agent Workflow Requirements

### 7.1 Agents

1. Lead Architect Agent
2. Network and Crawler Specialist
3. Data and Search Engineer
4. UI and Integration Expert
5. QA and Verificator Agent

### 7.2 Process Requirements

1. Each agent has explicit responsibilities
2. Agents interact via structured proposals and risk notes
3. Team Lead makes final decisions
4. All key decisions logged in workflow document

### 7.3 Mandatory Documentation

1. `multi_agent_workflow.md`
2. Per-agent description files under `agents/`

## 8. Acceptance Criteria (Gold Standard)

### 8.1 Functionality

1. Index endpoint accepts `origin` and `k`
2. Search returns required triple format
3. Duplicate pages are not crawled twice
4. UI can initiate index and search flows

### 8.2 Concurrency

1. Search requests succeed while indexing is active
2. Newly indexed results can appear without restart

### 8.3 Back-Pressure

1. Queue depth is visible
2. Throttling/back-pressure status is visible
3. System avoids unbounded queue growth

### 8.4 Recovery

1. Crawler state can be resumed after interruption
2. Snapshot files remain parseable and consistent

### 8.5 Multi-Agent Evidence

1. Workflow includes prompts, interactions, decisions
2. Agent files exist for every declared agent

## 9. Test Strategy

### 9.1 Unit Tests

1. Parser behavior
2. Crawler state controls
3. Search ranking + triple shaping

### 9.2 Integration Tests

1. `/index` to `/search` end-to-end
2. Dashboard/API consistency

### 9.3 Concurrency Tests

1. Index active while search queries run
2. Queue-pressure and throttle behavior

### 9.4 Recovery Tests

1. Interruption followed by resume
2. Snapshot load correctness

## 10. Deliverables

1. Working codebase
2. `README.md`
3. `product_prd.md`
4. `recommendation.md` (1-2 paragraphs)
5. `multi_agent_workflow.md`
6. Agent description files in `agents/`
