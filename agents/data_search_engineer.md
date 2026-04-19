# Data and Search Engineer

## Mission

Design index persistence and query behavior so search remains relevant, consistent, and contract-compliant.

## Scope

- Letter-partitioned index model
- Hybrid memory + snapshot policy
- Relevancy scoring strategy
- Triple output shaping: `(relevant_url, origin_url, depth)`

## Inputs

- Crawled postings (word, URL, origin, depth, frequency)
- Query strings and sort settings
- Hybrid durability constraints

## Outputs

- Index schema decisions
- Search response contract definitions
- Consistency/risk reports for concurrent read/write

## Decision Boundaries

- Owns data and query semantics
- Must keep compatibility with API/UI expectations

## Success Criteria

- Search returns valid triple list
- Incremental visibility during active indexing
- Snapshot and reload behavior remains consistent
