"""`scinumbers-monitor-grant`: make the view's database role, or rotate its password.

The view connects as `scinumbers_monitor`, a role that can read the trail and who is
enrolled, and nothing else (ADR-1310). The limit is the database's, not the view's:
a view that is read-only because nobody wrote a write stays read-only until somebody
does.

**Made in SQL, never in Neon's console or API.** A role made there joins
`neon_superuser`, which carries `pg_read_all_data` and `pg_write_all_data`, so it can
never be read-only whatever is granted afterwards (neon.com/docs/manage/roles, read
2026-10-02). A role made in SQL starts with nothing.

**Neon's read-only recipe is not followed, deliberately.** It grants `SELECT ON ALL
TABLES` and sets default privileges, which would hand over every tester's
OpenRouter key in `accounts` today and every future table automatically. Here a
table or a column is granted by name, in the change that reads it. Of `accounts` the
view reads `email` and `disabled`, because `pending.waiting` asks whether an address
is enrolled and not disabled; Postgres refuses any statement naming another column,
`select *` included.

Runs as the branch owner, resolved by name through Neon's API like `scinumbers-enrol`
-- no URL on disk. Every run sets a fresh password and prints it once: re-running is
how it is rotated. Nothing here stores it.
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys

from scinumbers_ask import neon, trail_store

from .connection import PASSWORD_ENV, ROLE

#: Neon requires at least 60 bits of entropy for a password set in SQL. 32 characters
#: from 62 is about 190.
PASSWORD_LENGTH = 32

#: Generous for a page, short enough that a runaway aggregate is cut off. Matches
#: `pending.STATEMENT_TIMEOUT_MS`, whose queries the door row reuses.
ROLE_STATEMENT_TIMEOUT = "30s"

NO_BRANCH = (
    "no branch named. Which environment should get the monitor's role? There is no "
    "default -- a role is per branch, and granting the wrong one leaves the view "
    "unable to read the branch you meant. Add --branch dev, then --branch alpha."
)

# Each statement its own `execute`, as in `trail_store`. The role is created only if
# absent, so a second run changes the password and re-applies grants rather than
# failing. `default_transaction_read_only` and the timeout are belt and braces: the
# grants already make every write impossible, and these make the intent visible to
# anyone listing the role's settings.
_CREATE = """
do $$ begin
    if not exists (select from pg_roles where rolname = '{role}') then
        create role {role} login;
    end if;
end $$
"""
_GRANTS = (
    "grant connect on database {database} to {role}",
    "grant usage on schema public to {role}",
    "grant select on {trail} to {role}",
    "grant select (email, disabled) on {accounts} to {role}",
    "alter role {role} set default_transaction_read_only = on",
    "alter role {role} set statement_timeout = '{timeout}'",
)


def new_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(PASSWORD_LENGTH))


def grant(engine, password: str, *, database: str = neon.DEFAULT_DATABASE) -> None:
    """Create or update the role on the branch `engine` is connected to, as its owner."""
    names = {
        "role": ROLE,
        "database": database,
        "trail": trail_store.DEFAULT_TABLE,
        "accounts": "accounts",
        "timeout": ROLE_STATEMENT_TIMEOUT,
    }
    with engine.begin() as conn:
        conn.exec_driver_sql(_CREATE.format(**names))
        # A password cannot be a bound parameter in DDL. `format(%L)` quotes it on
        # the server, so it is never spliced into SQL text on this side.
        statement = conn.exec_driver_sql(
            "select format('alter role %I password %L', %s::text, %s::text)", (ROLE, password)
        ).scalar_one()
        conn.exec_driver_sql(statement)
        for template in _GRANTS:
            conn.exec_driver_sql(template.format(**names))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scinumbers-monitor-grant", description=__doc__)
    parser.add_argument("--branch", help="Neon branch name, e.g. dev or alpha")
    parser.add_argument("--database", default=neon.DEFAULT_DATABASE)
    args = parser.parse_args(argv)
    if not (args.branch or "").strip():
        print(NO_BRANCH, file=sys.stderr)
        return 2

    missing = [n for n in ("NEON_API_KEY", "NEON_PROJECT_ID") if not os.environ.get(n)]
    if missing:
        print(f"set {' and '.join(missing)} first; nothing was changed", file=sys.stderr)
        return 2

    api_key, project = os.environ["NEON_API_KEY"], os.environ["NEON_PROJECT_ID"]
    branch = neon.branch_id(api_key, project, args.branch.strip())
    owner = neon.connection_url(api_key, project, branch, database=args.database)
    password = new_password()
    grant(trail_store.engine_from_url(owner), password, database=args.database)
    print(
        f"{ROLE} is ready on {args.branch}. Its password, shown once:\n\n  {password}\n\n"
        f"Set {PASSWORD_ENV} to it before running scinumbers-monitor. Running this "
        "again sets a new one."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
