# ADR-1260: The scheduled job holds a read-only role and a URL, not the Neon API key

- **Status:** accepted
- **Date:** 2026-10-02
- **Pull request:** none yet (`feat/first-use-notice`)

## Context

`scinumbers-pending` reaches the database through the Neon control plane
(`neon.branch_id`, `neon.connection_url`), which needs the organisation-scoped Neon
API key. That is right for an operator at a terminal. For a job that runs hourly on
GitHub's runners the same key would sit in a repository secret, and it can delete
the Neon project. The first-use query reads one table.

## Decision

The command reads **`SCINUMBERS_TRAIL_READ_URL`** and never calls `neon`. The URL
belongs to a login role created by `sql/first_use_reader.sql`, which the operator
runs once on the branch the deployment writes to (`alpha`):

- `select` on **three columns of the trail** — `at`, `event`, `user_email` — and not on
  the table: the other columns hold question text, feedback comments and session ids, and
  a review found the first draft granting the whole table. Not `accounts` either;
- `connect` on the database and `usage` on the schema, nothing more;
- `default_transaction_read_only = on` for the role.

**Two guards, one at each end.** The role cannot write or read anything else; and
`first_use._run` sets `set transaction read only` itself, so a more powerful URL
pointed at the command still cannot make asking a write. A guard belongs to the
operation, not to whoever calls it.

*Rejected:* the Neon API key in a secret (it can delete the project); a Postgres
owner URL (it can write everything).

## Trade-off accepted

One more thing to set up: the role is created per Neon branch, by hand, with a
password that must not be committed (the file carries an unquoted `<PASSWORD>`, a syntax
error until replaced, so a forgotten edit fails rather than creating a role with a known
password), and its URL becomes a repository secret. In return a leaked secret can read three columns — reader
addresses, the event names and their timestamps — and do nothing else.

**What was verified.** `tests/test_first_use_live.py` runs the *real*
`sql/first_use_reader.sql` against a throwaway role and table, with every
substitution asserted to have applied: the role can run the first-seen question;
`insert`, `update`, `delete` and `create table` are each refused; with the
read-only default overridden by `set transaction read write`, an insert is still
refused for lack of a grant (so the grants hold without the setting); and a second
table it was not granted cannot be read; and `detail`, a `session_id` filter and
`select *` on the granted table are each refused, while the first-seen question still runs
through the role on three columns. Run against the `secrets.toml` database,
outside the sandbox. **Not verified:** the role on `alpha` itself, through its
pooler with the URL the operator will build; and that a `drop role` from a
*non-owner* works, which the test's own cleanup needed a membership grant for.
