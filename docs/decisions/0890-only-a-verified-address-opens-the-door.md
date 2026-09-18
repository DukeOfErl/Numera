# ADR-0890: Only a verified address opens the door, and a missing claim refuses

- **Status:** accepted
- **Date:** 2026-09-18
- **Pull request:** _pending — `feat/open-enrolment`_

## Context

Enrolment is keyed on an email address: `accounts.lookup` matches the address the
provider asserts against a row the operator typed. With Google as the only
provider that was safe by accident — Google will not let anyone assert an address
they do not control.

ADR-0880 adds a provider with an open database connection, where anyone can
register any address and immediately be asserted as it. Without a further check,
registering an enrolled tester's address at Auth0 would sign you in **as that
tester**: their role, their credential, their conversation, and their name on
every record written. The system accepts no credential of its own and has nothing
else to distinguish the two.

OpenID Connect already carries the answer. The `email_verified` claim states
whether the provider has confirmed the address, and both Google and Auth0 send
it. Streamlit stores the ID token's claims whole (read from the installed 1.61.1,
`starlette_auth_routes.py` line 616), so it is available without a second call.

Two placements were considered.

- **Configure Auth0 to refuse a login until the address is verified** (an Action
  on the tenant), and trust what arrives. This is worth doing — it gives the
  reader Auth0's own "verify your email" page instead of ours — but as the *only*
  guard it protects exactly one caller, at one provider, through a setting
  nothing in this repository can see or test. A third provider added later
  inherits nothing.
- **Check it in `admit`**, where the door is decided.

## Decision

**`admit` refuses any account whose claims do not carry a true `email_verified`,
before the enrolment lookup**, as `Door.UNVERIFIED` with a sentence of its own.
`web.address_verified(claims)` is the rule, pure and testable without a browser:
exactly the boolean `True` or the string `"true"`.

**A missing claim refuses.** A provider that says nothing is one whose accounts
this app cannot tell apart from an impersonation. The two directions cost
differently — a wrongly refused reader reads one sentence and clicks a link they
already have, a wrongly admitted one reads somebody else's answers under their
name and writes records against it — so absence goes to the cheap side.

`1` is refused explicitly, because `1 == True` in Python and a truthy check would
admit whatever a provider happened to send.

**The refusal is decided fresh on every rerun, not held.** `end_session` does not
clear the held admission, so a cached refusal would outlive the reader signing
out, verifying and signing back in on the same tab — which is precisely the
sequence the sentence asks them to perform. Re-deciding is a dictionary lookup,
and the page an unverified reader sees has one button, so the record it writes is
bounded by their own clicks.

The check sits **before** the lookup, so an unverified address never reaches the
accounts table at all.

## Trade-off accepted

**A provider that omits `email_verified` shuts its users out entirely**, with a
sentence that tells them to check an email that may never arrive. Accepted: such
a provider is one this door cannot reason about, and the operator sees the
refusals in the trail. Google and Auth0 both send the claim.

**One more door, and one more sentence to keep distinct from "not enrolled".**
Five doors is more than a reader should ever need to hear about, but merging the
two would send half of each group to the wrong place: here the next step is the
reader's and it works, there it is the operator's and nothing on the page helps.

**The Auth0 Action is still worth setting**, and this decision does not replace
it. Both, for the reason the guard-placement convention gives: the driver keeps
the wording, the operation keeps the refusal.

## What was measured

Three defects seeded into a copy of the source against a green baseline of 106:

| Mutant | Killed |
|---|---|
| `claims.get("email_verified", True)` — absence admits | `test_address_verified_reads_the_claim_and_refuses_its_absence`, alone |
| the check's whole block replaced by a bare check below the enrolment lookup | `test_an_unverified_address_is_refused_with_its_own_sentence`, `test_an_unverified_address_is_never_looked_up` |
| `providers()` always offering `"default"` | `test_providers_reads_the_default_and_every_sub_table`, `test_a_provider_with_no_label_still_gets_a_button` |

A read-only verifier then measured the same claim from the other side, and the
claim held with no survivor: deleting the check kills three tests, and four
loosened predicates — `bool(value)`, `value is not None`, `value != False`,
`str(value).lower() == "true"` — all die. It also measured **both populations**
rather than reasoning about them, with an identical probe on `admit` in trees
built from this commit and its parent:

| | before | after |
|---|---|---|
| tests reaching an open door | 38 | 40 |
| admitted before and not after | — | none |
| refused as unverified | 0 | 3 |

That is the measurement this kind of change needs. Loosening or tightening a
rule moves records in both directions, and only one of them gets looked at.

Six gaps around the claim were found and closed, listed in the change's
`tasks.md` task 1.8. The one worth repeating here: **`st.login`'s argument was
unpinned in both directions**, while a comment beside it asserted that
`st.login()` and `st.login("default")` are different calls.

That second row was first written as "the check moved below the enrolment
lookup", and the verifier could not reproduce it: moving the block intact kills
one test, not two. The seed had also removed the record. **A seed is recorded as
the diff it was, not as the defect it was meant to stand for** — the kill list is
written down precisely so someone can re-run it, and a label that does not match
the diff makes the record worse than nothing.

Two things the next person seeding over `web.py` will meet, both of which produce
a red baseline and therefore no readable verdict: `LOGO` resolves through
`Path(__file__).parents[2]`, so `assets/` has to be linked into the copy; and
every page test loads `streamlit_app.py` through `parents[1]`, so it has to be
copied too when the tests are.
