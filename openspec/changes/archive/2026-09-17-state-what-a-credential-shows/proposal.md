## Why

A mutation run over `allowance`, `feedback` and `accounts` found five places where the code does the
right thing and nothing would notice if it stopped. Each survivor is the same shape: a test asserted
that a result had the expected *form* and never that it held the expected *content*, so blanking a
field, renaming a key or neutering a guard left the suite green.

None of the five is a bug today. What is missing is the requirement — the sentence that says which
behaviour was intended — and the test that would fail if it went. Three of them concern one thing an
interface states about a reader's credential, one concerns a rating's run label, and one concerns
what an operator is told when enrolment cannot be read.

The specific survivors:

- **The renewal period** (`limit_reset`) is read from the provider's payload and printed. Blanking
  it, renaming the key, or removing the `isinstance` guard around it all passed. The only test naming
  a renewal built the value by hand and never went through the parse.
- **A successful fetch** could have returned an empty allowance on *every* response: the two tests
  that called it with a real payload asserted only the outgoing request, never the answer. The probe
  beside it does assert its result, which is the shape the fetch was missing.
- **The provider's own `remaining`** is preferred over `limit - usage`. The fixture that exercised it
  had 5.0 − 1.6 = 3.4 and a `limit_remaining` of 3.4, so the two candidates were the same number and
  no test could tell which one was shown.
- **A rating's run label** could be blanked and the suite stayed green. The consequence is silent: a
  rating with no run label is a well-formed row that every grouping by run drops.
- **The reason enrolment could not be read** could be destroyed while the refusal itself survived.
  Two mutants did exactly that, and nothing noticed — leaving an operator a refusal with no clue
  which of a misconfigured address, an unreachable host and a refused password they are looking at.

## What Changes

- **A requirement about what the interface states about a credential**: the provider's own figures,
  or nothing. New, in `user-identity`; nothing in the spec covered the panel's figures at all.
- **A requirement that a rating carries the question's run label**, added to the requirement in
  `answer-feedback` that already governs what a rating names.
- **A requirement that the refusal preserves what could not be read** when enrolment is unreadable,
  added to the enrolment requirement in `user-identity`, which today says what a reader meets and
  nothing about what the operator is told. `accounts.lookup` already tries to do this and
  `trail_store.complain`'s docstring already promises the distinction; the requirement states it.
- **Tests for all five**, each driven from a payload or record whose fields are mutually
  distinguishable — a fixture in which two candidate figures happen to be equal is what hid the third
  survivor for a release.
- **Two blind tests repaired.** `test_an_empty_key_is_not_asked_about` and
  `test_an_empty_key_is_not_probed` raised their `AssertionError` from inside the opener, where
  `fetch` and `probe` catch every exception — so the assertion they exist to make could not fail.
  They now record the call and assert on the record, outside the swallowing handler.

No change to behaviour is proposed. Where a check finds that the code does not already satisfy the
requirement, that is a defect to fix; the deltas here describe what the code does today and what
nothing was holding it to.

## Capabilities

### New Capabilities

None. Both requirements land in specs that already exist.

### Modified Capabilities

- `user-identity`: one requirement added (what the interface states about a credential) and one
  modified (the enrolment refusal preserves what could not be read).
- `answer-feedback`: one requirement modified (a rating carries the question's run label).

## Impact

Tests: `tests/test_allowance.py`, `tests/test_feedback.py`, `tests/test_accounts.py`,
`tests/test_web_driver_identity.py`, and the mapping in `tests/test_spec_conformance.py`.

Source: none expected. The two source questions this change asks — whether `as_text` prefers the
provider's figure in every branch, and whether `feedback._record` can emit a null run label on any
real path — are answered in `tasks.md` with what was found.
