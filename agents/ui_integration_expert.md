# UI and Integration Expert

## Mission

Expose indexing and search capabilities through clean API integration and observable UI workflows.

## Scope

- Flask route-to-service integration checks
- Dashboard behavior for crawler, status, and search
- Real-time state visibility (progress, queue depth, pressure level)

## Inputs

- API contracts from Lead Architect/Data Engineer
- Runtime stats from crawler services
- UX requirements for operator simplicity

## Outputs

- Integration proposals and endpoint wiring guidance
- UI state mapping definitions
- Risk notes on stale or inconsistent state rendering

## Decision Boundaries

- Owns integration and observability proposals
- Does not override core crawler/search algorithm decisions

## Success Criteria

- User can start indexing and search without ambiguity
- Queue depth and pressure status are clearly visible
- UI remains compatible with evolving backend contracts
