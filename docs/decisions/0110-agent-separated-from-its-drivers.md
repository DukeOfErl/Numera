# ADR-0110: The agent is separated from its drivers by an event port

- **Status:** accepted
- **Date:** 2026-08-26
- **Pull request:** _pending — `feat/ask-agent`_

## Context

Three things need to put questions to this agent: a terminal, a web page, and an
evaluation harness. The path of least resistance is one class that knows which of
them is calling — a `mode` flag, an `interactive=True`, a caller name — and
adjusts what it prints and how much it explains.

Two constraints make that path unusable. The web framework re-runs its whole
script on every interaction, so an agent that blocks waiting for input cannot be
hosted in it at all. And the evaluation harness only measures something if the
agent behaves identically under it and under a person; an agent that can tell who
is asking can be tuned, deliberately or accidentally, to score well.

## Decision

The agent exposes a **port**: it accepts an `Ask(session_id, question)` and yields
typed events — `QuestionStarted`, `Retrieval`, `SpendWarning`, `CostProjection`,
`CitationWarning`, `Answer`, `AnswerEntries`, `QuestionEnded`. It reads no input
and writes no output. The terminal, the web page and the evaluation harness are
three **adapters** that render or record the same stream.

The agent takes no parameter naming its caller, and there is no branch inside it
on which driver is attached. A test asserts that the same question through an
attended and an unattended driver emits the same events.

Everything a conversation needs — the messages, the accumulated spend, the ceiling
in force — lives in the checkpoint, not in a driver. A driver holds the session
identifier and nothing else.

## Trade-off accepted

Every driver re-implements rendering. The terminal formats an ending as a line
with a dash; the web driver formats the same ending into an item and a caption.
Nothing enforces that the two say the same thing, and a warning added to the agent
can be rendered in one and silently dropped in the other — which is exactly what
happened when the web driver was first built (see ADR-0100).

What is bought is that a fourth driver costs an adapter and no change to the
agent, and that "the agent behaves the same however it is driven" is a property a
test can assert rather than a claim in a comment.
