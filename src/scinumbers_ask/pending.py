"""What is waiting for the operator, read out of the trail. Silent when nothing is.

Two things a reader can be stuck on that only the operator can clear: a
confirmation email that never arrived, and an address that is verified but not yet
enrolled. Both are already in the trail — `signin.resend_requested` and
`signin.refused` — so this asks rather than adds a mechanism.

**Silence is the contract.** With nothing waiting it prints nothing and exits 0, so
a daily `cron` line mails the operator only on the days something happened. A
monitor that reports "0 pending" every morning is one whose output stops being
read, and then the morning it says 1 goes unread too.

**A window, not a ledger.** Nothing marks a request as handled: the row stays in
the trail forever, because the trail is append-only and is not a work queue. So this
looks at a window — the last `--hours`, matching the interval it is run on — and
each request is therefore reported once. Miss a day and you miss those; query 2 of
`sql/signin.sql` is the wider net for people who gave up, and it is for reading
occasionally rather than on a schedule.

Read-only. It runs no `insert`, `update` or `delete`, which is why it is safe to
point at the branch the deployment writes to.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from . import neon, trail_store
from .enrol import MANAGEMENT_KEY_ENV, NEON_API_KEY_ENV, NEON_PROJECT_ENV, NO_BRANCH

#: Matches the interval the cron line in the README uses. A window rather than a
#: mark, for the reason the module docstring gives.
DEFAULT_HOURS = 24

#: One row per address, newest first. `make_interval` rather than string
#: interpolation into the interval, so the window is a bound parameter.
_WAITING = """
select detail->>'email' as address, max(at) as last_seen, count(*) as times
from {table}
where event = :event
  and detail->>'email' is not null
  and at > now() - make_interval(hours => :hours)
group by 1
order by max(at) desc
"""


@dataclass(frozen=True)
class Waiting:
    """One person, and how long they have been waiting."""

    address: str
    last_seen: object
    times: int


def _query(engine, event: str, hours: int, table: str) -> list[Waiting]:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text(f"set local statement_timeout = {trail_store.STATEMENT_TIMEOUT_MS}"))
        rows = conn.execute(
            text(_WAITING.format(table=table)), {"event": event, "hours": hours}
        ).all()
    return [Waiting(address=r[0], last_seen=r[1], times=r[2]) for r in rows]


def waiting(engine, *, hours: int = DEFAULT_HOURS, table: str = trail_store.DEFAULT_TABLE):
    """Who asked for their confirmation email again, and who is waiting to be enrolled.

    Returned rather than printed, so a second caller -- a test, a different
    report -- is not made to parse a report.
    """
    return (
        _query(engine, "signin.resend_requested", hours, table),
        _query(engine, "signin.refused", hours, table),
    )


def _report(no_email: list[Waiting], not_enrolled: list[Waiting], hours: int) -> str:
    """The lines to print, or "" when there is nothing to say."""
    if not no_email and not not_enrolled:
        return ""
    lines = [f"Waiting on you, from the last {hours} hours:", ""]
    if no_email:
        lines.append("  Never received the confirmation email — resend it at the provider:")
        lines += [f"    {w.address}  (asked {w.times}x, last {w.last_seen})" for w in no_email]
        lines.append("")
    if not_enrolled:
        lines.append("  Verified but not enrolled — scinumbers-enrol:")
        lines += [f"    {w.address}  (tried {w.times}x, last {w.last_seen})" for w in not_enrolled]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """`scinumbers-pending`. Prints nothing and exits 0 when nothing is waiting."""
    parser = argparse.ArgumentParser(
        prog="scinumbers-pending",
        description="Who is stuck at the door and needs the operator. Silent when nobody is.",
    )
    parser.add_argument(
        "--branch", help="REQUIRED, no default: the Neon branch the deployment writes to"
    )
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    parser.add_argument("--database", default=neon.DEFAULT_DATABASE)
    parser.add_argument("--role-name", default=neon.DEFAULT_ROLE, help="Neon database role")
    args = parser.parse_args(argv)

    if not args.branch:
        print(NO_BRANCH, file=sys.stderr)
        return 2
    # The management key is not read here: this asks the trail a question and
    # touches no provider. Naming only what it needs keeps the cron line from
    # carrying a credential that can mint keys.
    missing = [n for n in (NEON_API_KEY_ENV, NEON_PROJECT_ENV) if not os.environ.get(n)]
    if missing:
        print(f"set {' and '.join(missing)} first", file=sys.stderr)
        return 2
    if os.environ.get(MANAGEMENT_KEY_ENV):
        # Not fatal, and worth one line: a cron entry that sources the whole
        # enrolment env file hands a key that can mint credentials to a job that
        # only reads. Harmless here, and the kind of thing that stops being
        # harmless when somebody copies the cron line somewhere else.
        print(
            f"note: {MANAGEMENT_KEY_ENV} is set and is not needed by this command",
            file=sys.stderr,
        )

    api_key = os.environ[NEON_API_KEY_ENV]
    project = os.environ[NEON_PROJECT_ENV]
    try:
        branch = neon.branch_id(api_key, project, args.branch)
        url = neon.connection_url(
            api_key, project, branch, database=args.database, role=args.role_name
        )
    except Exception as exc:  # noqa: BLE001 - one sentence for the operator
        print(str(exc), file=sys.stderr)
        return 1

    engine = trail_store.engine_from_url(url)
    try:
        no_email, not_enrolled = waiting(engine, hours=args.hours)
    except Exception as exc:  # noqa: BLE001 - a silent monitor is the failure to avoid
        print(f"could not read the trail: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    report = _report(no_email, not_enrolled, args.hours)
    if report:
        print(report)
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point is the tested path
    raise SystemExit(main())
