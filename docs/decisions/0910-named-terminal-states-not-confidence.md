# ADR-0910: Every paper, field and candidate ends in a named state, never a confidence score

- **Status:** proposed
- **Date:** 2026-09-18
- **Pull request:** not yet opened — branch `feat/validator-prototype`

## Context

Stub. ADR-0040 and the loop-engineering brief both record that self-scored confidence is the least
reliable exit: the probe's blind arm was confidently wrong on the most famous number. The observed
structure of papers gives a closed set of situations instead — a value cited rather than measured, a
condition offloaded to a reference, a number stated only as a figure curve, a compiled literature
table.

## Decision

Per paper: `CLAIMS_FOUND`, `NOTHING_TO_EXTRACT`, `NOT_A_RESEARCH_ARTICLE`, `UNREADABLE`,
`CEILING_REACHED`, `FAILED`. Per condition field: `BESIDE_VALUE`, `FROM_METHODS`, `BY_REFERENCE`,
`SUPPLEMENTARY_ONLY`, `NOT_STATED`. Per candidate value: `MEASURED`, `DERIVED` (claims) and
`CITED`, `PARAMETER`, `COMPILED` (rejected, kept for the distractor pool). A bibliographic citation
marker on the clause holding a number is decisive for cited-versus-measured and outranks the verb,
so the JATS reader keeps markers as `[ref N]` tokens. See `design.md` D2.

## Trade-off accepted

To be completed with the options rejected (task 9.2).
