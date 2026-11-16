---
name: Architecture
description: >
  Use when making system-level architecture decisions, choosing between monolith and microservices,
  selecting architectural patterns, or designing system boundaries.
---

# Architecture

Start with a monolith, extract services only when forced by concrete scaling, team, or deployment constraints. Architecture is about trade-offs, not ideals.

## When to Use

- Starting a new system or major feature
- Evaluating whether to split a monolith
- Choosing between architectural patterns

## Monolith vs Microservices

| Factor | Stay Monolith | Consider Splitting |
|--------|--------------|-------------------|
| Team size | < 20 engineers | Independent teams need independent deploys |
| Deployment | Single pipeline works | One module's deploys block another's |
| Scaling | Uniform load | One component needs 10x resources |
| Data | Shared database is fine | Modules need different data stores |

**Default**: modular monolith with clean internal boundaries. Extract later; merging services back is painful.

## Architectural Patterns

| Pattern | Core Idea | Best For |
|---------|-----------|----------|
| Layered | UI -> Service -> Repository -> DB | Simple CRUD, small teams |
| Hexagonal | Business core with adapter edges | Multiple integrations |
| Clean Architecture | Dependencies point inward only | Complex domains needing testability |
| Event-Driven | Components communicate via events | Decoupled workflows, audit trails |
| CQRS | Separate read and write models | Read-heavy with complex queries |

## Hexagonal Architecture

The core knows nothing about HTTP, databases, or frameworks. Adapters translate between the outside world and the core's ports (interfaces). All dependency arrows point inward.

## Event-Driven Patterns

| Pattern | Use When |
|---------|----------|
| Event Notification | Loose coupling, eventual consistency OK |
| Event-Carried State | Subscribers shouldn't query back |
| Event Sourcing | Full audit trail, time-travel debugging |

## Service Communication

| Method | Coupling | Use When |
|--------|---------|----------|
| Synchronous (HTTP/gRPC) | Higher | Request/response, real-time |
| Async messaging (queue) | Lower | Background work, cross-service events |

## Boundary Design Rules

1. **One team, one service** -- org boundaries drive service boundaries
2. **Share contracts, not code** -- APIs and schemas, not libraries
3. **Own your data** -- each service owns its datastore
4. **Design for failure** -- every network call can fail

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Starting with microservices on day one | Start monolith, extract when pain is concrete |
| Distributed monolith | If they can't deploy independently, merge them |
| Sharing a database between services | Each service owns its data; sync via events or APIs |
| Architecture based on resume appeal | Choose based on team size and constraints |
| No module boundaries in the monolith | Define boundaries now so extraction is possible later |

## Attribution
**Original** -- Datatide, MIT licensed.
