---
name: Error Handling
description: >
  Use when designing error handling strategies, choosing between exceptions and result types,
  validating inputs, or building resilient systems in any language.
---

# Error Handling

Validate at the boundaries, trust internally. Errors are data -- handle them explicitly, propagate them intentionally, never swallow them silently.

## When to Use

- Designing input validation for an API or function boundary
- Choosing between exceptions, result types, or error codes
- Building retry logic or graceful degradation

## Error Strategy by Layer

| Layer | Strategy |
|-------|----------|
| External boundary (API, CLI) | Validate everything, return structured errors |
| Service/business logic | Typed errors or result types |
| Internal/private functions | Trust the caller, assert invariants |
| Infrastructure (DB, network) | Catch, wrap with context, propagate |

## Exception vs Result Pattern

| Aspect | Exceptions | Result/Either Types |
|--------|-----------|-------------------|
| Visibility | Hidden control flow | Explicit in signature |
| Composability | Try/catch nesting gets messy | Chains naturally |
| Best for | Truly exceptional situations | Expected failure modes |

**Rule of thumb**: if the caller should handle it, use a result type. If it's a programming error, throw.

## Validation Patterns

| Pattern | When to Use |
|---------|-------------|
| Parse, don't validate | Convert raw input into a typed, guaranteed-valid structure |
| Fail fast | Reject invalid input at the boundary immediately |
| Accumulate errors | Collect all failures, return them together |

## Error Propagation Rules

1. **Add context as errors bubble up** -- "failed to create order" wraps "connection refused"
2. **Don't catch what you can't handle** -- let it propagate
3. **Translate at boundaries** -- internal errors become user-facing messages at the API layer
4. **Log at handling, not throwing** -- avoid duplicate log entries

## Graceful Degradation

| Technique | Use Case |
|-----------|----------|
| Fallback value | Cached data when live source is down |
| Circuit breaker | Stop calling a failing service, fail fast |
| Retry with backoff | Transient network failures (exponential: 1s, 2s, 4s) |
| Partial success | Return what you can, report what failed |

Only retry idempotent operations. Add jitter to avoid thundering herd.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Catching all exceptions generically | Catch specific types, let unknown errors propagate |
| Swallowing errors silently (`catch {}`) | Log at minimum; prefer propagating with context |
| Returning null to signal failure | Use a result type or throw -- null is ambiguous |
| Validating deep inside business logic | Move validation to the boundary |
| Error messages exposing internals | Map to safe user-facing messages at the API layer |
| Retrying non-idempotent operations | Only retry when repeating the call is safe |

## Attribution
**Original** -- Datatide, MIT licensed.
