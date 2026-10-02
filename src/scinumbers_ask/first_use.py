"""Who has just been seen for the first time, read out of the trail. Silent when nobody.

A sibling of `pending.py` and the same kind of thing -- a harness command over the
trail that a scheduler runs with nobody watching -- with three differences that are
the reason it is not a flag on that one.

**It holds a database URL, not the Neon control plane.** `pending` resolves a branch
through `neon.py`, which needs the organisation-scoped API key; a scheduled job
holding that key could delete the project, and this reads one table. So it takes
`SCINUMBERS_TRAIL_READ_URL`, the URL of a role that can `select` from the trail and
nothing else (`sql/first_use_reader.sql`), and never *calls* `neon` (ADR-1260) --
importing `pending` for its timeouts loads that module, and a test asserts that
nothing in it is reached. The
credential is the first guard; `set transaction read only` below is the operation's
own, so a more powerful URL still cannot make asking a write (a guard belongs to the
operation, not to whoever happens to call it).

**It keeps no state.** "First" is derived: a reader is new for an event kind when
their earliest such event falls inside the window. Nothing is written to mark them
reported, which keeps the command read-only and safe to point at the live branch
(ADR-1250). The price is the window, see `DEFAULT_MINUTES`.

**It is one message per reader.** A reader whose first sign-in and first question
both fall in the window is one line, not two, because it is one person's arrival.

**Silence is the contract**, as for `pending`: with nobody new it prints nothing and
exits 0, so a scheduled run produces output only in an hour somebody arrived. A
failure to read is the opposite -- said loudly, exit 1 -- because silence would be
indistinguishable from a quiet hour.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from . import trail_store
from .pending import CONNECT_TIMEOUT_S, STATEMENT_TIMEOUT_MS

URL_ENV = "SCINUMBERS_TRAIL_READ_URL"

#: **Longer than the hourly interval on purpose, and which error that favours is the
#: point.** A tick GitHub delays or skips would leave a gap in an exactly-an-hour
#: window, and the reader who arrived in the gap would never be reported. With ten
#: spare minutes the window overlaps its neighbour: a reader is reported twice
#: instead of never. A repeated line costs a glance; a missed first reader costs the
#: moment it was worth knowing. Do not trim this to 60 -- that removes the overlap
#: and nothing fails until a tick is late. The delay actually seen is to be read out
#: of the keepalive's run history before this number is trusted (tasks 6.4).
DEFAULT_MINUTES = 70

#: One statement for both kinds, joined on the address, so a reader whose firsts
#: both landed in the window comes back as one row.
#:
#: `having min(at) > ...` is the whole of "first": it is true only when *no* earlier
#: event of that kind exists, because an earlier one would pull the minimum out of
#: the window. That needs the whole history -- unlike `pending`, the aggregate
#: cannot be bounded by `at` in the `where` -- and is cheap at this table's size
#: (a sequential scan of ~1,400 rows took 0.2 ms, measured 2026-10-02).
#:
#: `lower(user_email)` on both sides of the join: the trail carries the address as
#: the provider asserted it, and two spellings of one person must not read as two.
#: An empty string passes `is not null`, so it is excluded explicitly; a report line
#: with a blank address is one the operator cannot act on.
_FIRST_SEEN = """
with signed_in as (
    select lower(user_email) as address, min(at) as first_at
    from {table}
    where event = 'signin.admitted' and user_email is not null and user_email <> ''
    group by 1
    having min(at) > now() - make_interval(mins => :minutes)
),
asked as (
    select lower(user_email) as address, min(at) as first_at
    from {table}
    where event = 'question.asked' and user_email is not null and user_email <> ''
    group by 1
    having min(at) > now() - make_interval(mins => :minutes)
)
select coalesce(signed_in.address, asked.address) as address,
       signed_in.first_at as signed_in_at,
       asked.first_at as asked_at
from signed_in
full outer join asked on asked.address = signed_in.address
order by least(signed_in.first_at, asked.first_at)
"""

NO_URL = (
    f"set {URL_ENV} first: the URL of the read-only role (sql/first_use_reader.sql). "
    "It is deliberately not the Neon API key, which this command never reads."
)


@dataclass(frozen=True)
class FirstSeen:
    """One reader, and which firsts fell inside the window. A `None` is "not new"."""

    address: str
    signed_in_at: datetime | None
    asked_at: datetime | None


def _run(engine, statement: str, params: dict) -> list[tuple]:
    from sqlalchemy import text

    with engine.begin() as conn:
        # First in the transaction, which Postgres requires of this statement.
        conn.execute(text("set transaction read only"))
        conn.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        return conn.execute(text(statement), params).all()


def first_seen(
    engine,
    *,
    minutes: int = DEFAULT_MINUTES,
    table: str = trail_store.DEFAULT_TABLE,
    exclude: tuple[str, ...] = (),
) -> list[FirstSeen]:
    """Readers first seen inside the window. Returned rather than printed, so a test
    or a second report asks the question and does not parse a printout.

    Exclusions are applied here, **after** the two kinds are joined, so an excluded
    reader disappears whole instead of leaving half a row behind.
    """
    rows = _run(engine, _FIRST_SEEN.format(table=table), {"minutes": minutes})
    skipped = {address.lower() for address in exclude}
    return [FirstSeen(*row) for row in rows if row[0].lower() not in skipped]


def _when(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _report(readers: list[FirstSeen], minutes: int) -> str:
    """The lines to print, or "" when there is nothing to say."""
    if not readers:
        return ""
    lines = [f"First seen in the last {minutes} minutes:", ""]
    for reader in readers:
        firsts = []
        if reader.signed_in_at is not None:
            firsts.append(f"signed in {_when(reader.signed_in_at)}")
        if reader.asked_at is not None:
            firsts.append(f"first question {_when(reader.asked_at)}")
        lines.append(f"  {reader.address}  {', '.join(firsts)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """`scinumbers-first-use`. Prints nothing and exits 0 when nobody is new."""
    parser = argparse.ArgumentParser(
        prog="scinumbers-first-use",
        description="Who has just been seen for the first time. Silent when nobody has.",
    )
    parser.add_argument("--minutes", type=int, default=DEFAULT_MINUTES)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="ADDRESS",
        help="an address never to report (the operator's own, a test account); repeatable",
    )
    args = parser.parse_args(argv)

    if args.minutes <= 0:
        # Silence means nobody is new, so a window that can match nothing is a
        # confident all-clear manufactured by a bad argument. Refused, as `pending`
        # refuses it, rather than clamped.
        print(
            f"--minutes must be positive; {args.minutes} can never match anything",
            file=sys.stderr,
        )
        return 2
    url = os.environ.get(URL_ENV)
    if not url:
        print(NO_URL, file=sys.stderr)
        return 2

    engine = trail_store.engine_from_url(url, connect_args={"connect_timeout": CONNECT_TIMEOUT_S})
    try:
        readers = first_seen(engine, minutes=args.minutes, exclude=tuple(args.exclude))
    except Exception as exc:  # noqa: BLE001 - a silent monitor is the failure to avoid
        print(f"could not read the trail: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    report = _report(readers, args.minutes)
    if report:
        print(report)
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point is the tested path
    raise SystemExit(main())
