## Why

Enrolment is one command; withdrawal is two manual steps in two places, and
nothing links them. The operator disables the row in SQL and deletes the key in
the OpenRouter dashboard — and if they do only the first, the account is refused
while its credential stays live and spendable **without the app**, because the key
is stored in the clear and was given to the tester.

It could not be one command before: OpenRouter's Management API deletes a key by
its *hash*, which is returned once, at creation. `enrol` used the hash for its
compensating revoke and then discarded it, so nothing persisted could name the
key to the API.

## What Changes

- **`accounts` gains `openrouter_key_hash`**, written at enrolment. It is the only
  thing that can withdraw a credential through an API; without it a deployment
  holds live credentials it can revoke only by hand.
- **`scinumbers-withdraw <address> --branch <branch>`** disables the row and
  revokes the credential, in that order, and reports both facts.
- **The row is disabled, not deleted**: the trail rows the account wrote keep
  their attribution, and a table that still lists a withdrawn account is how an
  operator sees who once had access.
- **A row with no handle is disabled and said to be unwithdrawable.** The seven
  accounts enrolled before this column have none, and the command names the
  dashboard rather than guessing by key name — two keys can share a name after a
  `KeyLeftBehind`, and a withdrawal that revokes the wrong one is not correctable.

## Capabilities

### New Capabilities

None. `user-identity` gains a requirement.

### Modified Capabilities

- `user-identity`: a new requirement *"Withdrawing an account is one operator
  action, and it ends both halves of access"*; and the enrolment requirement gains
  the obligation to record what makes withdrawal possible later.

## Impact

**Code.** `sql/accounts.sql`: the column, and an `alter` for databases that exist.
`accounts.py`: `disable`, `Withdrawn`, and `insert` taking the handle. `enrol.py`:
`withdraw`, `withdraw_main`, `NotEnrolled`, `CredentialNotWithdrawn`, and one
shared branch-opening preamble where there were two. `pyproject.toml`: the script.

**Documentation.** README's enrolment section, `CHANGELOG.md`, ADR-1150.

**The operator must run `sql/accounts.sql` against each branch** before the first
enrolment after this lands, or the insert fails on a column that is not there.
