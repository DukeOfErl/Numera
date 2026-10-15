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

**Read-only.** It runs no `insert`, `update` or `delete` — resolution is a `join`
against records the app already writes — which is why it is safe to point at the
branch the deployment writes to.

**Verified against real Postgres on 2026-09-26**, `tests/test_pending_live.py`,
seven cases. Two runs of it found two defects: `jsonb_build_object` with a bound
parameter in the test's own helper, and -- the one that mattered --
`signin.refused` appearing in its own progress set, which emptied the enrolment
queue completely while every offline test passed. Neither was reachable by reading,
and the offline double cannot reach either, because it never runs the join.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from . import accounts, neon, trail_store
from .enrol import MANAGEMENT_KEY_ENV, NEON_API_KEY_ENV, NEON_PROJECT_ENV

#: Not `enrol.NO_BRANCH`, which talks about a row landing in the wrong branch and
#: enrolling a tester the app will never find. This command writes nothing, and an
#: operator debugging a failed cron job should not be told about rows.
NO_BRANCH = (
    "no branch named. Which environment should be read? There is no default -- "
    "the deployment's testers are in one branch and a rehearsal's are in another, "
    "and a silent answer from the wrong one is worse than no answer. "
    "Add --branch alpha."
)

#: Thirty days. Generous because the list now empties itself as problems resolve,
#: so the window is only there to age out an address that was abandoned rather than
#: to keep each report to one appearance. A daily run misses nothing inside it.
DEFAULT_HOURS = 24 * 30

#: **Progress is per stage, and one shared definition was a real bug.** The first
#: version unioned both proofs for both queries, which meant `signin.refused`
#: appeared in the progress set for the `signin.refused` query -- so every
#: unenrolled account resolved *itself* and the enrolment queue was permanently
#: empty. Offline tests could not see it: the double ignores the join. The live
#: test found it on its second run, which is the argument for having one.
#:
#: `user_email` is stamped onto every record of a signed-in session (ADR-0810), so
#: it is proof the door opened. `web.establish_identity` records `signin.admitted`
#: on arrival, stamped like anything else, so admission is observable even for a
#: reader who asks nothing -- which it was not at first, and which is how a solved
#: problem came to be reported every morning.
#: Bounded by the same window as the question it answers. Unbounded this is an
#: aggregate over the whole trail with no index on `user_email`, run twice per
#: invocation, under a 2000ms statement timeout chosen for single-row inserts on a
#: render path -- so a cold sequential scan would fail the check every morning. The
#: window costs nothing: progress older than the request cannot resolve it anyway.
_ADMITTED = """
select lower(user_email) as address, max(at) as at
from {table}
where user_email is not null
  and at > now() - make_interval(hours => :hours)
group by 1
"""

#: For the reader who never got their email, reaching the *enrolment* door is
#: progress: `signin.refused` sits behind the verified-address check (ADR-0890), so
#: it proves verification even though it is itself a problem. Their problem moved
#: on, and the other query picks them up.
#:
#: Note this is used for the resend queue only. The enrolment queue asks the
#: accounts table instead -- see `_UNENROLLED`.
_VERIFIED = (
    _ADMITTED
    + """
union all
select lower(detail->>'email') as address, max(at) as at
from {table}
where event = 'signin.refused'
  and detail->>'email' is not null
  and at > now() - make_interval(hours => :hours)
group by 1
"""
)

#: **The enrolment queue asks the authority, not the trail.** Inferring it from
#: later sign-ins was wrong in both directions. A tester enrolled who does not come
#: back was reported for thirty days, and following the advice failed with
#: `AlreadyEnrolled`; worse, an enrolled account with no credential or a rejected
#: one meets `NO_CREDENTIAL` or `CREDENTIAL_REJECTED`, where the page stops before
#: `establish_identity` runs and `admit` writes no refusal either -- so nothing was
#: ever recorded again and they were misreported indefinitely. Whether somebody is
#: enrolled is a row in `accounts`, in this same database, and that is what to ask.
#:
#: A disabled row counts as not enrolled, matching `accounts.lookup`, which refuses
#: a withdrawn account exactly as an absent one.
_UNENROLLED = """
with asked as (
    select lower(detail->>'email') as address, max(at) as last_seen, count(*) as times
    from {table}
    where event = 'signin.refused'
      and detail->>'email' is not null
      and detail->>'email' <> ''
      and at > now() - make_interval(hours => :hours)
    group by 1
)
select asked.address, asked.last_seen, asked.times
from asked
where not exists (
    select 1 from {accounts} a
    where lower(a.email) = asked.address and not a.disabled
)
order by asked.last_seen desc
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
      -- An empty string passes `is not null`. `request_resend` falls back to ""
      -- when the claim is unreadable at click time, and a report line with a blank
      -- address is one the operator cannot act on.
      and detail->>'email' <> ''
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


#: This command's own, not `trail_store`'s 2000ms. That figure bounds a single-row
#: insert on the render path, where a slow write must not delay an answer. These are
#: aggregates over a growing table in an unattended batch job, and the cost of
#: waiting is nothing while the cost of a spurious failure is a monitor the operator
#: learns to ignore.
STATEMENT_TIMEOUT_MS = trail_store.BATCH_STATEMENT_TIMEOUT_MS

#: Likewise the connect timeout. `trail_store.CONNECT_TIMEOUT_S` is 5s and its own
#: comments record that a Neon free-tier cold start can outrun it -- and a 09:00
#: daily run is the guaranteed-cold case, since nothing has touched the branch
#: overnight. One attempt that times out prints a failure, so the check would
#: false-alarm most mornings, which is the same wasted-mail outcome as reporting a
#: quiet day.
CONNECT_TIMEOUT_S = trail_store.BATCH_CONNECT_TIMEOUT_S


def _run(engine, statement: str, params: dict) -> list[Waiting]:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        rows = conn.execute(text(statement), params).all()
    return [Waiting(address=r[0], last_seen=r[1], times=r[2]) for r in rows]


def waiting(
    engine,
    *,
    hours: int = DEFAULT_HOURS,
    table: str = trail_store.DEFAULT_TABLE,
    accounts_table: str = accounts.DEFAULT_TABLE,
):
    """Who is **still** stuck: asked for their email and never got verified, or got
    verified and is still not enrolled.

    Returned rather than printed, so a second caller -- a test, a different
    report -- is not made to parse a report.
    """
    resend = _STILL_WAITING.format(table=table, progress=_VERIFIED.format(table=table))
    return (
        # Verification *or* admission clears "never got the email": both prove the
        # address works.
        _run(engine, resend, {"event": "signin.resend_requested", "hours": hours}),
        # Whether somebody is enrolled is a row, not an inference -- see `_UNENROLLED`.
        _run(engine, _UNENROLLED.format(table=table, accounts=accounts_table), {"hours": hours}),
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
    if args.hours <= 0:
        # Silence means nobody is stuck, so a window that can match nothing is a
        # confident all-clear manufactured by a bad argument. Refused rather than
        # clamped: the operator meant something, and it was not this.
        print(f"--hours must be positive; {args.hours} can never match anything", file=sys.stderr)
        return 2
    # The management key is not read here: this asks the trail a question and
    # touches no provider. Naming only what it needs keeps the cron line from
    # carrying a credential that can mint keys.
    missing = [n for n in (NEON_API_KEY_ENV, NEON_PROJECT_ENV) if not os.environ.get(n)]
    if missing:
        print(f"set {' and '.join(missing)} first", file=sys.stderr)
        return 2
    if os.environ.get(MANAGEMENT_KEY_ENV) and sys.stderr.isatty():
        # **Only to a terminal**, and that condition is the whole point. The
        # documented cron line sources the enrolment env file, whose first line is
        # this variable -- so without the check the note went to stderr on every
        # scheduled run, cron mailed it, and the operator got mail every morning.
        # That is exactly the "output stops being read, and then the morning it says
        # 1 goes unread too" failure this command is built to avoid, introduced by a
        # note warning about something harmless. A person at a prompt can act on it;
        # a cron job cannot.
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

    engine = trail_store.engine_from_url(url, connect_args={"connect_timeout": CONNECT_TIMEOUT_S})
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
