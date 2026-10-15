# ADR-1150: Withdrawing an account revokes the key, disables the row, and keeps it

- **Status:** accepted
- **Date:** 2026-09-29
- **Pull request:** _pending — `feat/withdrawing-an-account`_

## Context

Enrolment has been one command since ADR-0900. Withdrawal was two, in two places,
with nothing linking them: disable the row in SQL, delete the key in OpenRouter's
dashboard. Doing only the first is the easy mistake and the expensive one — the
account is refused by the app while its credential stays live, and since the key
is stored in the clear and was handed to the tester, **it can be spent without the
app at all**. The app's refusal is not a spending control.

It could not be one command. OpenRouter's Management API deletes a key by its
*hash*, returned once, at creation. `enrol` used the hash for its compensating
revoke when the insert failed, then discarded it; `accounts` stored the key, not
the hash. So nothing that survived enrolment could name the key to the API.

Three questions had to be answered, and the second two are where the reasoning is.

## Decision

**Store the handle.** `accounts.openrouter_key_hash`, written at enrolment. The
alternative was to find the key by name at withdrawal time — `enrol` names each
key after the address, so a listing could be matched. Rejected: two keys can carry
one name after a `KeyLeftBehind`, and a withdrawal that revokes the wrong tester's
key is not a mistake the operator can correct, because the revoked one is gone and
the live one is unchanged. An exact handle refuses instead of guessing.

**Disable the row; do not delete it.** The trail rows the account wrote keep their
attribution (ADR-0810 — a judgement's weight is the weight it carried when
given), and a table that still lists a withdrawn account is how an operator sees
who once had access. Deleting the row loses that while keeping the address in the
trail anyway, so it buys tidiness and pays in memory. It also makes a
re-enrolment look like a first one.

**Disable first, then revoke, and that order is the decision rather than an
implementation detail.** Both halves can fail, so the question is which partial
state to leave behind:

- *Refused account, live credential* — recoverable by a person at the dashboard,
  and the command says exactly which key. The reader meets "not enrolled", which
  is true.
- *Admitted account, revoked credential* — the reader signs in, asks, and meets a
  provider error they cannot act on and the operator has not been told about.

The first is strictly better, and disabling first also yields the handle from the
same statement, so no window exists in which the row has been read and the next
step is not yet decided.

**A withdrawal reports only what it did.** Three states look alike from the
outside and are not: an account with a credential that was revoked, one whose
credential *was already gone* (the command run twice, or the key deleted at the
dashboard first), and one that never had a credential at all. Reporting the
second as a live key sends the operator hunting something that does not exist,
and the third as a live key sends them hunting something that never existed —
both are false alarms about the one thing this command has to be trusted about.
So a 404 from the revoke is success, and whether the row ever held a key is read
from the row (`openrouter_key is not null`) rather than inferred from the missing
handle, which both the second and third states share.

A row carrying a key and no handle — the accounts enrolled before this column — is
disabled and then reported as unwithdrawable, naming the dashboard. Half the job done and
the other half named is the honest outcome; claiming a withdrawal that did not
happen is the one thing worse than refusing.

## Trade-off accepted

**A column that is null for every existing row.** The seven accounts enrolled
before this cannot be withdrawn through the API, and no backfill is offered for
the reason the name-matching option was rejected. They are withdrawable as far as
being refused, which is the half that matters for access through the app.

**A revoked key stays in the row.** `openrouter_key` is not cleared, so a
withdrawn account still shows `has_key`. Clearing it would mean a third statement
after the revoke, and losing the handle before the revoke is confirmed would make
a failed withdrawal unretryable. `disabled` beside it says what happened.

**Re-enrolment is refused, not handled.** Keeping the row makes withdrawal
reversible in principle, and nothing exposes that: `scinumbers-enrol` on a
withdrawn address mints a key, meets the unique index, revokes the key it just
minted and refuses. The refusal now says *which* kind of duplicate it met, because
"already enrolled" is true of a withdrawn row and reads as the opposite, and
`sql/accounts.sql` carries both statements. Doing it properly — reinstating with a
fresh capped credential, under an explicit flag — is deferred, and the flag is the
point: enrolment quietly reinstating whatever a mistyped address happened to match
among the withdrawn is how somebody gets a credential nobody meant to issue.

**The schema changed under a running deployment.** `sql/accounts.sql` is
idempotent and carries the `alter`, but an enrolment run against a branch where it
has not been applied fails on a missing column. That is in the change's tasks as
an operator step, and it fails loudly rather than silently — an insert naming a
column that is not there cannot half-succeed.
