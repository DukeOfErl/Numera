# ADR-0790: The session cap is a heartbeat registry, not a per-address limit

- **Status:** accepted
- **Date:** 2026-09-16
- **Pull request:** _pending — `feat/user-identity`_

## Context

A hosted deployment needs a bound on how many sessions it holds open at once.
Each open session is an agent, a conversation in the checkpoint store, and —
while a question runs — a model call in flight; a host with a fixed memory and
a fixed number of workers has a number above which it stops answering anyone.

The roadmap called this "rate limiting", and the first thing to record is what
it is **not**: it is not cost control. Every tester's questions are funded by a
credential with its own monthly cap (ADR-0780, ADR-0820), so the budget is
already bounded per person and a session cap adds nothing to it. This guard
protects the *host*. Reading it as a spend control would lead someone to tune it
against the wrong quantity.

Two ways to count were on the table:

- **Per client address**, the conventional rate limit. Streamlit exposes
  `st.context.ip_address` — and its own documentation says the value is supplied
  by the client and must not be used for security. Behind a proxy every visitor
  shares one address; from a determined visitor, every request has a different
  one. It is not evidence of anything.
- **Per session, by heartbeat.** Streamlit re-runs the script on every
  interaction and offers no reliable disconnect hook, so the only observable
  fact about a session is *when it last ran*. A registry of `session_id →
  last seen`, touched on every rerun and pruned of entries older than an idle
  window, is the count.

## Decision

**`web.SessionRegistry`, one per server under `st.cache_resource`, keyed on the
browser session** — the per-tab token, *not* the conversation. Under sign-in one
account is one conversation across all its tabs (ADR-0830), so counting
conversations would count accounts: eight testers with five tabs each is forty
Streamlit sessions and forty agents, which is exactly what the cap exists to
bound, reported as eight. Each entry remembers which conversation its tab is in,
which is what lets pruning clear that conversation's identity stamp and panel
rows once its *last* tab has gone and not while another is open. Every rerun of an admitted session touches it. A new
session arriving when the live count is at `SCINUMBERS_MAX_SESSIONS` (default 20)
is shown one sentence — try again shortly — and is not recorded, so a refused
visitor holds no place. An admitted session is never ended to make room: the cap
refuses the door, it does not clear the room. Entries idle longer than
`SCINUMBERS_SESSION_IDLE_S` (default 600) are pruned, and pruning also evicts the
session's entry in the identity registry and its rows in the dev panel's sink,
which are keyed the same way.

**Counted at the door, not before it — revised 2026-09-16.** The first version
counted every visitor before sign-in was offered, on the reasoning that the cap
should also bound OAuth round trips. That claim is withdrawn. Streamlit's login
callback returns to the bare base URL, so the pre-sign-in visit and the signed-in
one are different sessions, and counting the first left a place held by every
sign-in for the length of the idle window — the cap ran out with a fraction of
its sessions real. What costs the host is a session with an agent behind it, and
that is what is now counted. OAuth round trips are bounded by the provider, not
here.

**Admitting prunes, so it must run before the stamp is established.** A reader
returning after the idle window does both in one script run; with the stamp set
first, pruning wiped it in the same run and the question they came back to ask
was recorded against nobody while the sidebar still named them. The driver calls
`session_registry().admit(...)` and then `establish_identity(...)`, and a test
drives that order rather than a convenient one.

**The registry is locked.** Streamlit runs one script thread per browser session
against this single cached object, so two reruns prune concurrently — and the
second `del` on an already-removed key raised, handing that reader a stack trace
instead of the app. A check-then-set on the count could also admit over the cap.

**A tab already holding a conversation is admitted whatever the count.** Pruning
is by heartbeat, so a reader who steps away past the idle window loses their
entry; without this they returned mid-conversation to a try-later page, which is
precisely the "no open session is ended" the message promises. `continuing` is
the driver's statement that this tab already has a transcript, and it is the one
way past a full cap.

**Nothing reads the client's address**, and a test asserts that over the source
of the two files that could.

## Trade-off accepted

**The registry over-counts, and the ADR exists so nobody corrects for it.** A tab
closed without a further interaction stays "live" until its idle window passes;
in the worst case the deployment admits `MAX_SESSIONS` minus the number of
recently-closed tabs, not `MAX_SESSIONS`. That is the cheap direction: a guard
for the host that admits *fewer* than configured costs a visitor a few minutes'
wait, where one that admitted more would cost everyone the host. An operator who
sees the app turning people away below the configured number is seeing this,
and the fix is a shorter idle window or a higher cap made knowingly — not a
correction that counts closed tabs as gone.

**It is an approximation of "open", not a measurement of it.** A real disconnect
signal would make this exact; Streamlit does not offer one, and a websocket-level
hook would tie the driver to the framework's internals. Accepted, with the idle
window as the knob.

**It does not protect against one person opening many tabs**, each a new session
— it was never meant to; that is a person, enrolled and funded by their own
credential, whose questions are bounded by it. The cap bounds the *total*, which
is the host's concern, and leaves the per-person bound to the credential.
