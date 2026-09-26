"""What is waiting for the operator, read out of the trail. Silent when nothing is.

Two things a reader can be stuck on that only the operator can clear: a
confirmation email that never arrived, and an address that is verified but not yet
enrolled. Both are already in the trail — `signin.resend_requested` and
`signin.refused` — so this asks rather than adds a mechanism.

**Silence is the contract.** With nothing waiting it prints nothing and exits 0, so
a daily `cron` line mails the operator only on the days something happened. A
monitor that reports "0 pending" every morning is one whose output stops being
read, and then the morning it says 1 goes unread too.

**Only what is still stuck.** The first version reported everything inside a
window, on the grounds that nothing marks a request as handled — and that was wrong
twice over. It reported people whose problem had since resolved, which is the noise
that teaches an operator to skip the mail; and it missed the fact that **the trail
already says who got through**. An address the identity stamp wrote as `user_email`
was admitted, because the stamp lands only on a session that passed the door
(ADR-0810); an address later seen as `signin.refused` got past *verification*,
because that door is behind the verified check (ADR-0890). So resolution is
derived, not tracked, and no new column or state is needed:

- *never got the email* resolves on any later sign of verification — a
  `signin.refused` or an admitted session;
- *verified but not enrolled* resolves on a later admitted session.

Anything still unresolved keeps being reported until it is fixed, which is what
makes a daily run worth reading: the list is the work, and it empties as the work is
done. The window survives as `--hours`, no longer as the mechanism but as a bound
on how far back to look, so an address abandoned months ago ages out rather than
nagging forever.

Read-only, and both queries are read-only by construction: resolution is a `join`
against records the app already writes.

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

#: Thirty days. Generous because the list now empties itself as problems resolve,
#: so the window is only there to age out an address that was abandoned rather than
#: to keep each report to one appearance. A daily run misses nothing inside it.
DEFAULT_HOURS = 24 * 30

#: Two kinds of proof that a reader got somewhere, unioned.
#:
#: `user_email` is stamped onto every record of a signed-in session (ADR-0810), so
#: it is proof the door opened. **It was not enough on its own**, and that is the
#: defect this query was shipped with: the door recorded only refusals, so a reader
#: who signed in and asked nothing wrote no record at all, and their solved problem
#: went on being reported every morning. Found by an operator watching a resolved
#: row refuse to disappear. `web.establish_identity` now records `signin.admitted`
#: on arrival, which is stamped like anything else -- so this arm covers it without
#: naming it, and admission is observable for the first time.
#:
#: `signin.refused` sits *behind* the verified-address check (ADR-0890), so it
#: proves verification even though it is itself a problem: someone who asked for
#: their email and then reached that door got what they needed.
_PROGRESS = """
select lower(user_email) as address, max(at) as at
from {table}
where user_email is not null
group by 1
union all
select lower(detail->>'email') as address, max(at) as at
from {table}
where event = 'signin.refused' and detail->>'email' is not null
group by 1
"""

#: Lower-cased on both sides of the join: the trail carries the address as the
#: provider asserted it and as the accounts row spells it, and `accounts.lookup`
#: folds case, so two spellings of one person must not read as two people.
#: `make_interval` rather than interpolation, so the window is a bound parameter.
_STILL_WAITING = """
with asked as (
    select lower(detail->>'email') as address, max(at) as last_seen, count(*) as times
    from {table}
    where event = :event
      and detail->>'email' is not null
      and at > now() - make_interval(hours => :hours)
    group by 1
),
progress as (
    select address, max(at) as at from ({progress}) as p group by 1
)
select asked.address, asked.last_seen, asked.times
from asked
left join progress on progress.address = asked.address
where progress.at is null or progress.at < asked.last_seen
order by asked.last_seen desc
"""


@dataclass(frozen=True)
class Waiting:
    """One person, and how long they have been waiting."""

    address: str
    last_seen: object
    times: int


def _query(engine, event: str, hours: int, table: str) -> list[Waiting]:
    from sqlalchemy import text

    statement = _STILL_WAITING.format(table=table, progress=_PROGRESS.format(table=table))
    with engine.begin() as conn:
        conn.execute(text(f"set local statement_timeout = {trail_store.STATEMENT_TIMEOUT_MS}"))
        rows = conn.execute(text(statement), {"event": event, "hours": hours}).all()
    return [Waiting(address=r[0], last_seen=r[1], times=r[2]) for r in rows]


def waiting(engine, *, hours: int = DEFAULT_HOURS, table: str = trail_store.DEFAULT_TABLE):
    """Who is **still** stuck: asked for their email and never got verified, or got
    verified and is still not enrolled.

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
    days = hours / 24
    span = f"{days:.0f} days" if days >= 2 else f"{hours} hours"
    lines = [f"Still waiting on you (looking back {span}):", ""]
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
