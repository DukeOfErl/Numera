# ADR-0010: Adopt OpenSpec for spec-driven development

- **Status:** accepted
- **Date:** 2026-08-07
- **Pull request:** commit `7e6e937` on `chore/openspec-setup`

## Context

The project was starting from an empty `uv` scaffold, and its subject matter is unusually
specification-heavy: the goal is a database of biological numbers whose value depends entirely on
whether claims can be verified against sources. Decisions such as what counts as "supported by the
source", how an unverifiable entry differs from an unsupported one, and how a benchmark is scored
are behavioural commitments that must outlive any particular implementation.

Most of the work is carried out by coding agents. Left unstructured, agents tend to fuse three
distinct questions — why a change is wanted, what behaviour it must produce, and how it is built —
into a single burst of code, which makes the reasoning unreviewable and the behaviour
undocumented.

`CLAUDE.md` already mandated architecture decision records, a changelog, and a requirements
document, but nothing enforced the separation between behavioural commitments and implementation
choices, nor tracked whether a change had been thought through before code was written.

Options considered: ad-hoc planning driven by `CLAUDE.md` conventions alone; conventional issue
tracking; or a spec-driven workflow tool.

## Decision

Adopt OpenSpec (`@fission-ai/openspec`) with its `spec-driven` schema as the planning system. Each
change is scaffolded with `openspec new change` and progresses through four artifacts with an
enforced dependency order: `proposal.md` (why, and which capabilities are affected), `specs/`
(implementation-agnostic requirements with concrete scenarios), `design.md` (technical choices), and
`tasks.md` (the implementation checklist, and the only artifact required before applying). Accepted
specs are promoted into `openspec/specs/` as the project's durable behavioural record.

## Trade-off accepted

Every non-trivial change now carries planning ceremony before implementation, and a workflow
dependency on a third-party tool and its file layout — including the risk that the tool's own
conventions drift. In exchange, behavioural requirements are recorded separately from implementation
detail and survive refactors, agents receive explicit per-artifact instructions instead of improvising
structure, and `openspec validate` mechanically catches changes that declare capabilities without
specifying them. For a project whose entire premise is verifiable claims, an unspecified system
would have been a poor advertisement for its own thesis.
