---
name: Type Safety
description: "Use when leveraging type systems to prevent bugs at compile time — covering generics, contracts, narrowing, and using types as documentation."
---

# Type Safety

Types are both documentation and guardrails. A good type system catches entire categories of bugs before code ever runs, and communicates intent more reliably than comments.

## When to Use

- Designing function signatures, data models, or API contracts
- Choosing between structural and nominal typing approaches
- Using generics to write reusable yet safe code
- Narrowing types to eliminate impossible states

## Types as Documentation

Types tell the next developer (and your future self) what is expected without reading the implementation.

| What Types Communicate | Example |
|----------------------|---------|
| Valid inputs | A function accepting `PositiveInt` vs `int` |
| Possible outcomes | Return type `Result<User, NotFoundError>` vs `User | null` |
| State constraints | `VerifiedEmail` vs `string` |
| Relationships | `Map<UserId, Permissions>` vs untyped dictionary |

**Rule:** If you write a comment explaining what a value can be, you should express it as a type instead.

## Structural vs Nominal Typing

| Approach | How It Works | Tradeoff |
|----------|-------------|----------|
| **Structural** | Types match if their shapes match | Flexible; easy interop; accidental matches possible |
| **Nominal** | Types match only by declared name/identity | Strict; prevents accidental substitution; more ceremony |

Use nominal types (branded types, newtypes, tagged types) when you need to distinguish values that share a shape — e.g., `UserId` vs `OrderId` even though both are strings.

## Generics

Generics let you write logic once and apply it safely across types.

| Principle | Detail |
|-----------|--------|
| Constrain generics | Bound type parameters to what the function actually needs |
| Prefer composition | `Container<T>` over inheritance hierarchies |
| Avoid over-generalization | If only used with one type, don't make it generic yet |
| Name meaningfully | `T` is fine for simple cases; use `TItem`, `TKey`, `TValue` for clarity |

## Type Narrowing

Narrowing reduces a broad type to a specific one through runtime checks, eliminating impossible branches.

| Technique | When to Use |
|-----------|-------------|
| Discriminated unions | Model states with a shared tag field (`status: "loading" | "success" | "error"`) |
| Guard functions | Validate and narrow at boundaries (API input, deserialization) |
| Exhaustiveness checks | Ensure all union variants are handled; compiler errors on missed cases |
| Assertion functions | Narrow and throw in one step at trust boundaries |

## Design by Contract

| Contract | Mechanism |
|----------|-----------|
| **Preconditions** | Input types and validation — what must be true before calling |
| **Postconditions** | Return types — what the caller can rely on |
| **Invariants** | Type constraints maintained throughout an object's lifetime |

Make illegal states unrepresentable. If a combination of fields is invalid, restructure the type so it cannot exist.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using primitive types for domain concepts | Create distinct types: `EmailAddress`, `UserId`, `Money` |
| Casting or forcing types to silence errors | Fix the underlying type mismatch; casts hide bugs |
| Optional fields for mutually exclusive states | Use discriminated unions to model state transitions |
| Generics with no constraints | Add bounds so the compiler can verify usage |
| Ignoring exhaustiveness warnings | Handle every variant; let the compiler catch missing cases |

## Attribution
**Original** — Datatide, MIT licensed.
