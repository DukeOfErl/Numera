# ADR-0780: Accounts live in the trail database, keys in the clear

- **Status:** accepted
- **Date:** 2026-09-16
- **Pull request:** _pending — `feat/user-identity`_

## Context

Each tester's questions are funded by a runtime credential of their own, minted
by the operator at OpenRouter's Management API with a hard monthly cap
(roadmap §WP3, verified 2026-09-16). At sign-in the application has to turn an
email into a role and that credential, and the operator has to be able to enrol
someone — add the row, assign the role, paste the key — without a redeploy.

Where that mapping lives was open. Four options:

- **Streamlit secrets.** A `[roles]` table in `secrets.toml`, which the example
  file once sketched. Rejected in the roadmap before this change: every
  enrolment is a redeploy, and a credential per tester in the secrets box is a
  secrets box that grows with the tester list.
- **A second database**, for the accounts alone. A second URL in secrets, a
  second engine, a second failure mode and a second thing to back up — for an
  isolation the threat model does not need, because the runtime keys are the
  least valuable thing in either database.
- **The trail database, with the key column encrypted.** Defends against a
  reader who has the database but not the application's secrets. Costs a second
  secret (the encryption key, which then has to live in the secrets box the
  first option was rejected for growing), and a decryption on every sign-in.
- **The trail database, keys in the clear.** One URL, one engine, one place to
  look. The URL is already a secret.

## Decision

**An `accounts` table in the same Neon database as `trail`, read through the
same engine, with `openrouter_key` stored in the clear.** `sql/accounts.sql`
carries the DDL and the operator's templates; `scinumbers_ask.accounts.lookup`
reads one row by email at sign-in and nowhere else.

Why in the clear is acceptable, stated so it can be re-examined:

- Every key is minted with a hard monthly limit and `limit_reset: monthly`. The
  worst a leaked key does is spend one tester's month.
- Every key is revocable in one call (`DELETE /api/v1/keys/{hash}`), and
  `disabled` on the row withdraws it from the application without the call.
- The database URL was already a secret, because the table beside this one now
  holds testers' questions verbatim (ADR-0840) — which is the more sensitive
  column in the database. A reader who has the URL has that already.

**Enrolment fails closed** — `lookup` raises `EnrolmentUnavailable` when the
table cannot be read, and the page admits nobody — because a tolerance that
failed open would let a database outage open the door. That is the deliberate
opposite of the trail's own fail-open (ADR-0710); `accounts.py` says so where
the two sit side by side.

## Trade-off accepted

**The trail database now holds credentials.** Its URL has to stay a secret for a
second reason as well as the first, and `secrets.toml.example`'s rule — exactly
one URL, never a spare — matters more than it did. If a key without a cap is ever
stored here, this decision has to be made again, because the argument above rests
on the cap.

**One database is one blast radius.** A compromised trail URL yields the
accounts, and a compromised accounts row yields nothing about the trail that the
URL did not already yield. Accepted as the same radius the trail already had.

**No user-management page, by design.** Enrolment is a row an operator inserts.
That is what makes `manage accounts` not a permission (roadmap §WP3): there is no
code path in the application to refuse. A helper script for minting keys and
inserting rows is a later convenience, not part of this decision.
