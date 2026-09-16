# ADR-0840: What a question's trail keeps, and why

- **Status:** proposed
- **Date:** 2026-09-16
- **Pull request:** `feat/…` — to be filled when the change is implemented

> **Stub, allocated with the change** (`add-question-and-answer-records`, block
> `0840`–`0870`). Written out when the decision is implemented, not as a batch at
> the end — by then the rejected options are gone and what survives is a
> description of the code.

## Context

To be written. The shape: the trail records `question_id` but neither the
question nor the answer, so a rating names something that cannot be read.

## Decision

To be written. Three records rather than one; the question recorded at the start
so a failing run still leaves one; cited and retrieved kept separable.

## Trade-off accepted

To be written. Row size, and the obligation created by keeping what somebody
typed.
