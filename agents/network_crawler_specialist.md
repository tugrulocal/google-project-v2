# Network and Crawler Specialist

## Mission

Design and validate reliable crawl execution using native Python networking and threading primitives.

## Scope

- URL frontier and queue operations
- Deduplication and normalization flow
- Rate limiting and back-pressure mechanics
- Crawl lifecycle behavior under load

## Inputs

- Index contract (`origin`, `k`)
- Runtime limits (`hit_rate`, queue capacity)
- Domain filtering rules

## Outputs

- Crawl algorithm proposals
- Queue pressure strategies
- Risk notes for deadlocks, stalls, overload

## Decision Boundaries

- Owns crawler behavior proposals
- Must align with Lead Architect governance and Team Lead final decisions

## Success Criteria

- No duplicate crawl of normalized URLs
- Controlled behavior under queue pressure
- Stable pause/resume/stop behavior
