# ADR-0920: The reviewer always sees two texts; the second's kind is recorded and never shown

- **Status:** proposed
- **Date:** 2026-09-18
- **Pull request:** not yet opened — branch `feat/validator-prototype`

## Context

Stub. The mechanical quote check passes any sentence that contains the number, including one that
merely mentions it. The reviewer is the check for that, and a two-way choice forces reading. A
choice offered only sometimes would itself carry information about the item.

## Decision

Every item carries two texts from the same paper. The second is a **distractor** (adjacent
condition, cited value, different quantity, parameter, derivation half — in that preference order)
or a **second occurrence** of the same value. Admissibility is mechanical: a distractor may not
contain the value, its rounding or its unit conversion, nor be a recorded occurrence of the claim.
No admissible second text means no item. The kind and type are stored on the item and never
rendered. See `design.md` D5.

## Trade-off accepted

To be completed with the options rejected (task 9.2).
