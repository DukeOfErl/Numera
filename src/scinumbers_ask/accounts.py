"""Who is enrolled: one row per account, read once at sign-in, refused loudly.

`lookup` is the whole module. It is on the agent's side of the dependency line
for the same reason `authorization` is -- a test or a second caller has to be
able to ask "is this person enrolled" without a browser -- and it imports no
framework; the driver hands it the engine `st.connection` built.

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
