# Multi-Agent Workflow

## 1. Purpose

This document explains how HW2 was designed and managed with a multi-agent collaboration process.

The project goal is two-fold:

1. Build a working crawler and search system on localhost.
2. Demonstrate clear multi-agent collaboration, prompt design, interaction flow, and decision governance.

## 2. Team Topology

### 2.1 Lead Architect Agent

Owns system-wide architecture, PRD consistency, workflow governance, and final proposal synthesis for Team Lead approval.

### 2.2 Network and Crawler Specialist

Owns URL frontier, crawl scheduling, deduplication, rate limiting, and queue/back-pressure mechanics.

### 2.3 Data and Search Engineer

Owns index data structures, persistence/snapshot strategy, and relevance/triple shaping for search output.

### 2.4 UI and Integration Expert

Owns Flask endpoint integration with dashboard UX and real-time status visibility (queue depth, throttle state, progress).

### 2.5 QA and Verificator Agent

Owns test matrix, verification reports, and Gold Standard requirement compliance checks.

## 3. Collaboration Protocol

Agents communicate through normalized artifacts:

1. `TaskBrief`
2. `Proposal`
3. `RiskNote`
4. `DecisionRequest`
5. `VerificationReport`

### 3.1 Message Templates

#### TaskBrief

- Objective
- Inputs
- Constraints
- Deadline
- Owner

#### Proposal

- Option description
- Benefits
- Cost/complexity
- Impacted modules

#### RiskNote

- Risk statement
- Trigger conditions
- Severity
- Mitigation

#### DecisionRequest

- Candidate options
- Agent recommendations
- Lead Architect synthesis
- Requested Team Lead decision

#### VerificationReport

- Tested scope
- Pass/fail outcomes
- Residual risks
- Release recommendation

## 4. Decision Authority

1. Agents propose and challenge options.
2. Lead Architect consolidates technical direction.
3. Team Lead makes final decision.
4. Final decision becomes binding for implementation.

## 5. Implemented Key Decision (HW2)

### 5.1 Topic

How to support search while indexing is active.

### 5.2 Chosen Model

Hybrid:

- Memory working set for low-latency active reads
- Periodic disk snapshots for durability and resume

## 6. Agent Debate Log

### Debate 01: Search during active indexing

- Network and Crawler Specialist onerdi: memory-first indexing path to minimize read/write lock wait.
- Data and Search Engineer riski belirtti: memory-only model crash durumunda veri kaybi ve replay maliyeti yaratir.
- UI and Integration Expert onerdi: dashboard tarafinda anlik gorunurluk icin incremental search sonuclari gerekir.
- QA and Verificator Agent riski belirtti: disk-only tasarim latencyyi artirir ve active indexing altinda testleri kirmaya yatkindir.
- Lead Architect sentezi: Hybrid model, latency ve durability dengesini en iyi kurar.
- Team Lead karari: Option 2 (Hybrid) kabul edildi.

### Debate 02: Back-pressure policy

- Network and Crawler Specialist onerdi: queue depth hard-cap + hit-rate cap birlikte kullanilsin.
- Data and Search Engineer riski belirtti: sadece queue cap kullanilirsa ani yukte write amplification olabilir.
- QA and Verificator Agent onerdi: pressure seviyeleri icin testlenebilir esikler tanimlanmali.
- Lead Architect sentezi: pressure status = normal/warning/critical; her seviyede belirli davranis.
- Team Lead karari: pressure seviyeleri PRD acceptance criteria'ya eklenecek.

## 7. Prompt Strategy by Agent

### Lead Architect prompt style

- Align with HW2 contract.
- Preserve native-only constraints.
- Force explicit trade-off summaries.

### Network and Crawler Specialist prompt style

- Focus on queue correctness, dedup guarantees, and load control.
- Report lock scope and blocking points.

### Data and Search Engineer prompt style

- Focus on index consistency, triple output compliance, and scoring behavior.
- Ensure backward compatibility for UI metadata.

### UI and Integration Expert prompt style

- Keep operator flow simple and observable.
- Make queue depth and back-pressure states visible.

### QA and Verificator prompt style

- Convert requirements into measurable checks.
- Reject untestable assumptions.

## 8. Required Evidence Checklist

- Workflow file present (`multi_agent_workflow.md`)
- Agent description files present (`agents/*.md`)
- PRD reflects Team Lead decisions
- README references workflow artifacts
- Decision logs contain recommendation + risk + final decision
