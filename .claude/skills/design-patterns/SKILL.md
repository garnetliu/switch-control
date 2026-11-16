---
name: Design Patterns
description: >
  Use when making structural design decisions, applying SOLID principles, choosing between
  inheritance and composition, or deciding when to introduce an abstraction.
---

# Design Patterns

Prefer composition over inheritance, wait for three concrete cases before abstracting. Patterns are tools, not goals -- apply them when they solve a real problem.

## When to Use

- Structuring a new module or service
- Refactoring rigid or tangled code
- Deciding whether to introduce an interface or abstraction

## SOLID Quick Reference

| Principle | Rule | Smell When Violated |
|-----------|------|-------------------|
| Single Responsibility | One reason to change | God objects, files over 300 lines |
| Open/Closed | Extend without modifying | Switch statements that grow with every feature |
| Liskov Substitution | Subtypes must be substitutable | Overrides that throw "not supported" |
| Interface Segregation | No unused method dependencies | Interfaces with 10+ methods |
| Dependency Inversion | Depend on abstractions | Hard-coded `new DatabaseClient()` in business logic |

## The Rule of Three

| Situation | Action |
|-----------|--------|
| First occurrence | Write it inline |
| Second occurrence | Note the duplication, resist the urge |
| Third occurrence | Extract -- you now see the real pattern |

Premature abstraction creates the *wrong* abstraction. YAGNI until proven otherwise.

## Composition vs Inheritance

| Factor | Inheritance | Composition |
|--------|------------|-------------|
| Coupling | Tight -- child depends on parent internals | Loose -- depends on interface |
| Flexibility | Fixed at compile time | Swappable at runtime |
| Depth limit | 2 levels before it hurts | No practical limit |

**Default to composition.** Use inheritance only for genuine type hierarchies with shared behavior.

## Essential Patterns

| Pattern | Problem It Solves |
|---------|------------------|
| Strategy | Swappable algorithms behind one interface |
| Observer | Decoupled event notification |
| Factory | Complex object creation without exposing construction |
| Adapter | Wrap incompatible interface to match your contract |
| Repository | Abstract data access from business logic |

## DDD Core Concepts

| Concept | Guideline |
|---------|-----------|
| Entity | Identity-based, equality by ID |
| Value Object | Immutable, equality by value |
| Aggregate | All mutations through the root |
| Bounded Context | Same word can mean different things across boundaries |
| Ubiquitous Language | Code names match business terms |

Use DDD when the domain is complex. For CRUD apps, it's overhead.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Abstracting on first occurrence | Wait for the Rule of Three |
| Deep inheritance (3+ levels) | Flatten with composition |
| Pattern for pattern's sake | Only apply when it solves a concrete problem |
| Anemic domain models | Put behavior on the objects that own the data |
| God class doing everything | Split by responsibility |

## Attribution
**Original** -- Datatide, MIT licensed.
