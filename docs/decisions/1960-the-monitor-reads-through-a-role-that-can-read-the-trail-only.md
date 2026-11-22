# ADR-1960: The monitor reads through a role that can read the trail and who is enrolled, nothing else

- **Status:** accepted
- **Date:** 2026-10-02
- **Pull request:** _pending — `feat/monitor-dashboard`_

## Context

`numera-pending` connects as `neondb_owner`, which can read and write
everything. The monitor's spec requires the view to be unable to write and unable
to read a credential, and requires that limit to belong to the database, not to
the queries the view happens to issue. `accounts` holds each tester's
`openrouter_key`.

Facts that shaped this, read from neon.com/docs on 2026-10-02:

- A role made in Neon's console or API is a member of `neon_superuser`, which
  brings `pg_read_all_data` and `pg_write_all_data`. Such a role can never be
  read-only.
- A role made in SQL starts with nothing, and its password needs at least 60 bits
  of entropy.
- Neon's documented read-only recipe grants `SELECT ON ALL TABLES` and sets default
  privileges. That would include `accounts` today and every future table.

The door row reuses `pending.waiting`. Its enrolment query reads `accounts.email`
and `accounts.disabled`, so a role that could not read `accounts` at all would make
the door rule fork.

Two practical constraints. `psql` is not installed on the operator's machine. And
it is undocumented whether Neon's API will reveal a URI for a role made in SQL.

## Decision

`numera-monitor-grant --branch <name>` (`grant.py`) creates `numera_monitor`
in SQL as the branch owner, resolving the owner through Neon's API by branch name,
as `numera-enrol` does. It grants:

- `CONNECT` and `USAGE ON SCHEMA public`;
- `SELECT ON trail`;
- `SELECT (email, disabled) ON accounts`, a column grant. Postgres refuses any
  statement that names another column, `select *` included.

It sets `default_transaction_read_only = on` and a role `statement_timeout`. It
grants no default privileges and nothing `ON ALL TABLES`. Each run sets a fresh
generated password and prints it once. Re-running is how the password is rotated.

The view never asks Neon for a URI. It takes the host from `neon.endpoint_host`,
the branch's read-write endpoint, which carries no credential. It takes its own
password from `NUMERA_MONITOR_DB_PASSWORD`. Streamlit is started with
`--secrets.files` pointing at an empty file: a verifier found that, run from the
repository root, Streamlit loads `.streamlit/secrets.toml` at server start, and
that file holds the owner's URL. `test_monitor_cli.py` measures it with
Streamlit's own loader, the file read without the flag and ignored with it. So
the view neither fetches the owner's URL nor loads it. This also made the planned probe (task 1.1)
unnecessary: whether the API reveals SQL-role passwords no longer matters.

`tests/test_monitor_role_live.py` probes the grants on a real branch. It runs each
forbidden statement in an explicitly read-write transaction, so it measures the
grants and not the read-only default, and it rolls every probe back. The owner
runs the same probes first as the canary.

## Trade-off accepted

Temporary tables are not refused. Postgres grants `TEMPORARY` on a database to
`PUBLIC` by default, so the role can probably create and fill a temporary table
in its own session. It vanishes at disconnect and touches no shared row.
Revoking it from `PUBLIC` would change every role's privileges, the app's
included, to close a hole that holds nothing. Not measured: the live probes test
`create table` in `public` only.

One more secret for the operator to hold: the monitor's password, in the
environment. It is a read credential for testers' emails and comments, which is
why the view binds to 127.0.0.1.

A table or column the view later needs must be granted by name, by re-running the
command after editing it. The view errors on a missing grant rather than
silently reading more, which is the cheap direction.
