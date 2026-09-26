"""Who is enrolled: one row per account, read once at sign-in, refused loudly.

`lookup` reads a row and `insert` writes one, and they are together because the
table's shape is the thing worth keeping in one place: the case-folding rule
below governs both, and a second module writing this table would be a second
copy of that rule to keep in step. `insert` has one caller -- the enrolment
command -- and is here rather than beside it for that reason.

Both are on the agent's side of the dependency line for the same reason
`authorization` is -- a test or a second caller has to be able to ask "is this
person enrolled" without a browser -- and neither imports a framework; the driver
hands `lookup` the engine `st.connection` built, and the command builds its own.

**This fails closed, and that is the opposite of the trail store beside it.**
`trail_store.record` swallows every failure because the cost of a dropped row is
one line of a dataset read by eye. Here the cost of tolerating a failure is
admitting everyone: if the accounts table cannot be read and `lookup` answered
`None`, the page would say "not enrolled" -- truthful -- but a tolerance that
answered "enrolled" or fell back to some default would let a database outage
open the door. So an unreachable table raises `EnrolmentUnavailable`, distinct
from "not enrolled", and the page shows a different sentence for it. The two
modules disagree on purpose; a reader who makes them consistent will pick the
wrong direction for one of them (ADR-0710 for the trail's side; the design of
`add-user-identity` for this one).

What comes back is the account and its credential. The credential travels to
the agent alone; the rest of `Account` -- who, as what -- stops at the driver.
"""

from __future__ import annotations

from dataclasses import dataclass

from .permissions import Identity, Role
from .trail_store import STATEMENT_TIMEOUT_MS, complain

DEFAULT_TABLE = "accounts"

#: Matched case-insensitively, and the row's own spelling is what comes back.
#:
#: The address is typed by the operator into `sql/accounts.sql` and asserted by
#: the identity provider, and nothing makes those two agree on case. An exact
#: match refuses `Tester@example.org` for a row enrolled as `tester@example.org`
#: -- a person told they are not enrolled when they are, which is the expensive
#: direction here: the operator looks at the table, sees the row, and has nothing
#: to go on. Mailbox names are case-sensitive in the standard and case-folded by
#: every provider this deployment will meet; folding is the direction that
#: matches reality.
_SELECT = """
select email, role, openrouter_key, disabled
from {table}
where lower(email) = lower(:email)
"""


class AlreadyEnrolled(RuntimeError):
    """This address already has a row. Nothing was written.

    Raised from the database's own refusal rather than from a select this module
    ran first: two operators enrolling the same address at the same moment would
    both pass a select and the second would still have to be refused here. The
    unique index is the thing that actually decides, so it is the thing asked.
    """


class EnrolmentUnavailable(RuntimeError):
    """The accounts table could not be read. Nobody is enrolled until it can be.

    Not the same as "not enrolled", and the page must not say the same thing for
    both: a tester told they are not enrolled during an outage asks the operator
    to enrol them, and the operator finds them already there.
    """


@dataclass(frozen=True)
class Account:
    """An enrolled account as the driver reads it off the row."""

    email: str
    role: Role
    #: `None` when the operator has enrolled the account but issued no key yet;
    #: the page then refuses asking and names the missing credential.
    openrouter_key: str | None

    @property
    def identity(self) -> Identity:
        """Who, and as what -- the part of this that is stamped onto the trail.

        One place, so that a field added to `Identity` reaches the stamp without
        a second hand-written conversion to keep in step. The credential stays
        out of it deliberately: it goes to the agent and nowhere else.
        """
        return Identity(self.email, self.role)


def lookup(engine, email: str, *, table: str = DEFAULT_TABLE) -> Account | None:
    """The enrolled account for `email`, or `None` if there is none.

    `None` for an absent row and for a disabled one -- withdrawn is refused the
    same way as never enrolled, and the row is kept so the trail rows it wrote
    stay attributed. `None` also for a row whose `role` is not one of `Role`'s
    values: that is an operator's typo in `sql/accounts.sql`, and the safe
    direction is to refuse and say so on stderr rather than to grant a role
    nobody chose.

    Raises `EnrolmentUnavailable` when the table cannot be read, for the reason
    the module docstring gives. Under the trail store's statement timeout, so
    a hung database refuses in two seconds rather than never.
    """
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            conn.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))
            row = conn.execute(text(_SELECT.format(table=table)), {"email": email}).first()
    except Exception as exc:
        raise EnrolmentUnavailable(f"{type(exc).__name__}: {exc}") from exc
    if row is None or row.disabled:
        return None
    try:
        role = Role(row.role)
    except ValueError as exc:
        complain(f"account {email!r} has a role that is not one of {[r.value for r in Role]}", exc)
        return None
    return Account(email=row.email, role=role, openrouter_key=row.openrouter_key or None)


#: Both constraints on the address mean the same thing to an operator. The
#: primary key catches an exact repeat, `accounts_email_lower` catches one that
#: differs only in case, and which fires is not a distinction anybody enrolling a
#: tester can act on -- so `insert` does not read the index name out of the error.
#: Matching on the name would also go quietly false the day the index is renamed,
#: and the failure would be a duplicate reported as an unknown database error.
#: Postgres `unique_violation`. psycopg exposes it as `sqlstate` on the driver
#: error under SQLAlchemy's wrapper.
_UNIQUE_VIOLATION = "23505"

_INSERT = """
insert into {table} (email, role, openrouter_key)
values (:email, :role, :key)
"""


def insert(engine, email: str, role: Role, key: str, *, table: str = DEFAULT_TABLE) -> Account:
    """Enrol one account. Raises `AlreadyEnrolled` if the address already has a row.

    The row's own spelling of the address is what goes in, unfolded: `lookup`
    folds when it matches, so the operator's capitalisation is preserved for
    display without affecting who is found. Any failure that is not a duplicate
    raises as itself -- an unreachable database, a missing table and a refused
    password are all things the operator has to see, and this is a command they
    are watching rather than a page they are reading.

    Under the trail store's statement timeout, so a hung database refuses in two
    seconds rather than never.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    try:
        with engine.begin() as conn:
            conn.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))
            conn.execute(
                text(_INSERT.format(table=table)),
                {"email": email, "role": Role(role).value, "key": key},
            )
    except IntegrityError as exc:
        # Narrowed to SQLSTATE 23505, unique_violation. Every `IntegrityError`
        # reported as "already enrolled" is right against today's schema, where
        # only the primary key and `accounts_email_lower` can fire -- and wrong
        # the day a `check` on `role` or a `not null` column is added, when the
        # operator would be sent looking for a row that is not there while the
        # freshly minted key was silently withdrawn. The code is the database's
        # own, not the index's name, so it survives the index being renamed.
        if getattr(getattr(exc, "orig", None), "sqlstate", None) != _UNIQUE_VIOLATION:
            raise
        raise AlreadyEnrolled(f"{email} is already enrolled") from exc
    return Account(email=email, role=Role(role), openrouter_key=key or None)
