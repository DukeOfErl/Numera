# ADR-0820: One agent per session, handed a credential and never an identity

- **Status:** accepted
- **Date:** 2026-09-16
- **Pull request:** _pending — `feat/user-identity`_

## Context

Two facts about the code as it stood before `add-user-identity`:

- `default_model()` read `OPENROUTER_API_KEY` from `os.environ` — one key per
  process.
- `web.resources()` built the `AskAgent` under `@st.cache_resource` — one agent
  per server, shared by every browser session.

Per-tester credentials (roadmap §WP3: minted by the operator at OpenRouter with
a monthly cap each, so one tester's questions cannot spend another's allowance)
break both. The key has to reach the agent as a value, and each session has to
have an agent of its own to hold it.

Once the agent takes a per-person parameter, the question is *which* facts about
the person it takes. The first draft passed an `Identity(email, role)` at
construction so the agent could put them on its trail records. That works. It
also puts the role one attribute away from the code that decides an answer, with
nothing but discipline keeping it from being read there — and the spec
`user-identity` says the role and the account shall not reach the agent, and
that what the agent is handed shall be identical whoever asks.

ADR-0110 already established that the agent takes no parameter naming its
*caller*, so it cannot behave one way for a person and another for the
evaluation harness. This is the same principle one step further in: it takes no
parameter naming the *person* either.

## Decision

**`AskAgent.__init__` gains `api_key: str | None = None` and nothing else.**
`default_model(config, api_key)` uses it; `None` falls back to the environment,
which is what the terminal, the evaluation harness and a deployment with no
identity configured pass — their behaviour is unchanged. `ask`'s signature does
not change.

**The web driver builds one agent per browser session**, into `st.session_state`,
with the account's key. The corpus repository — the expensive index — stays
under `@st.cache_resource` and is shared. An `AskAgent` is a config, a
repository reference and a checkpoint path; its saver is opened per call. One
per tab costs nothing worth measuring.

**Identity is stamped at the sink, not threaded through the agent** (ADR-0810
for the mechanism). Consequences, each of them the point:

- `agent.py`, `trace.py` and `feedback.py` are untouched by identity: no
  parameter, no field, no import.
- What the agent is given is identical whoever asks, *by construction*: it is
  never given who is asking. Asserted behaviourally — two roles, same question,
  the model doubles' `seen` lists compared — and structurally, in
  `tests/test_driver_independence.py`, which parses the three modules and fails
  on any identifier from `{Identity, identity, role, email, account, user_role,
  user_email}`. A seeded `role` parameter on the constructor fails that test.
- The CLI and the harness install no filter, so their records carry NULL exactly
  as before. "Unconfigured behaves as before" is not a branch; it is the absence
  of a filter.

**The principle, recorded for the day it is needed:** if the agent must ever know
what is permitted — a question whose scope needs allowing, a calculation a role
may request — it is handed the *permissions*, never the role. An answer may then
depend on what is allowed and never on who is asking, and the grant table stays
the one place that maps one to the other.

## Trade-off accepted

**The credential is the one per-person fact the agent does hold**, and a
credential identifies a person to the operator (it was issued to them). Accepted:
the agent needs it to reach the provider at all, it is opaque to the model — it
travels in a header, never in a prompt — and nothing in the agent reads it
except to construct the client. It is still a per-person value inside the core,
and the structural test deliberately does not list `api_key` as a forbidden
identifier.

**An agent per session means the checkpoint path is shared between agents.**
It was already shared between sessions through one agent; sessions are separated
by thread id inside the store, and that does not change. What is new is several
`AskAgent` objects over one SQLite file, each opening its own saver per call —
the same access pattern as before with more objects.

**A stale identity in a long session.** Enrolment is read once at sign-in and the
identity held for the session (design, "read once per session"). A role changed
mid-session takes effect on the next sign-in, not the next question. The row is
cheap to re-read, and if this matters it is one call.
