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


class UnusableAddress(ValueError):
    """The address cannot be stored or matched as it stands. Nothing was written."""


def usable(email: str) -> str:
    """The address as it will be stored and matched, or a refusal.

    Surrounding whitespace is **stripped** and anything else odd is **refused**,
    and the asymmetry is the decision. A trailing newline off a heredoc or a
    pasted line is the operator's tool, not their intent, and trimming it costs
    nothing; whitespace or a control character *inside* an address is a paste
    that went wrong, and quietly rewriting it would enrol an address nobody
    asked for.

    Both directions of getting this wrong were paid for. `dev.accounts` holds a
    row keyed `'yoav.g.pollack@gmail.com\\n'`: it was accepted, it looks right in
    every listing that prints it unquoted, and no provider will ever assert a
    claim that matches it -- so the account exists, is enabled, and admits
    nobody. The person meets "not enrolled", the operator looks at the table and
    sees their row sitting there, and nothing on either side says why. That is
    the expensive direction, and it is expensive precisely because it is silent.

    Refusing is the cheap direction: it costs the operator one sentence, at the
    moment they are watching a command they just ran. The sentence quotes the
    address with `repr` so an invisible character is visible in it -- an error
    naming `yoav@example.org` when the string ends in a newline is the same
    mistake told twice.

    In the operation, not in the command (`.claude/rules/identity.md`): `insert`
    calls this, so a second caller -- a test, a migration, a future web page --
    gets the same refusal without knowing it exists.
    """
    cleaned = email.strip()
    if not cleaned:
        raise UnusableAddress("an address is required; this one is empty or only whitespace")
    if any(character.isspace() for character in cleaned):
        raise UnusableAddress(f"{email!r} has whitespace inside it, and an address cannot")
    if any(character < " " or character == "\x7f" for character in cleaned):
        raise UnusableAddress(f"{email!r} has a control character in it, and an address cannot")
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise UnusableAddress(f"{email!r} is not an address: it needs a name, an @ and a domain")
    return cleaned


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

    # The same rule as `insert`, read in the other direction and with the other
    # answer: a claim this module cannot match is "not enrolled", never an
    # exception. The door has a sentence for that and none for a malformed
    # claim, and inventing one would be a new refusal for a case no provider
    # produces -- while raising here would take the page down instead.
    try:
        email = usable(email)
    except UnusableAddress as refused:
        complain(f"a sign-in claim carried an address that cannot be matched: {refused}", refused)
        return None
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


@dataclass(frozen=True)
class Withdrawn:
    """A row that has just been disabled, and the handle to its credential.

    `key_hash` is `None` where the account had no credential, and where it was
    enrolled before the hash was stored -- two different situations that look the
    same from here, which is why the caller reports both as "withdraw the key by
    hand" rather than claiming to know which.
    """

    email: str
    key_hash: str | None


def disable(engine, email: str, *, table: str = DEFAULT_TABLE) -> Withdrawn | None:
    """Refuse this account from now on, and hand back the handle to its credential.

    `None` where there is no such row. Disabling rather than deleting: the trail
    rows the account wrote keep their attribution, and a table that still lists a
    withdrawn account is how an operator sees who once had access.

    One statement, so the row cannot be read and then found changed. **It does not
    revoke anything** -- the credential lives at another provider and this module
    reaches no network. `enrol.withdraw` is the operation that does both, in the
    order that leaves the safe state behind when the second half fails.
    """
    from sqlalchemy import text

    email = usable(email)
    with engine.begin() as conn:
        conn.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        row = conn.execute(text(_DISABLE.format(table=table)), {"email": email}).first()
    if row is None:
        return None
    return Withdrawn(email=row.email, key_hash=row.openrouter_key_hash)


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
insert into {table} (email, role, openrouter_key, openrouter_key_hash)
values (:email, :role, :key, :key_hash)
"""

#: Disabling and reading the handle in one statement, so no window exists in which
#: the row is readable and the operator's next step is not yet decided.
#:
#: Unconditional rather than `and not disabled`: an account disabled by hand whose
#: key was never revoked is exactly the case a withdrawal command exists for, and
#: a `where` that skipped it would report "no such account" for a row plainly
#: there. Running it twice is harmless -- the second `update` sets what is already
#: set -- and the revoke that follows meets its own 404.
_DISABLE = """
update {table} set disabled = true
where lower(email) = lower(:email)
returning email, openrouter_key_hash
"""


#: Read only to choose a sentence, never to decide anything. The insert has
#: already been refused by the time this runs.
_DISABLED = """
select disabled from {table} where lower(email) = lower(:email)
"""

#: What a duplicate says when the row it collided with has been withdrawn. The
#: plain "already enrolled" is true there and reads as "this person has access",
#: which is the opposite of the case -- and the operator's next step is different:
#: there is nothing to reconsider, there is a row to clear.
#:
#: Rewritten once, shorter. The first version explained *why* the row is kept
#: before saying what to do, which is the wrong order for something read at a
#: prompt: the operator wants the state and the next step, and the reasoning is
#: in ADR-1150 where someone can go looking for it.
#:
#: "key revoked" is what `scinumbers-withdraw` does and not something this row
#: records -- a row disabled by hand, or one whose revoke was refused, says the
#: same thing here. Kept because the common case is the command, and because the
#: operator's next step is the same either way; if it ever misleads, the honest
#: form is "withdrawn" with nothing in the brackets.
#:
#: Re-enrolment is deliberately **not** offered here (ADR-1150): reinstating a
#: withdrawn account is its own operation, and doing it as a side effect of
#: `enrol` would hand a new credential to whoever a mistyped address happened to
#: match among the withdrawn.
WITHDRAWN_ALREADY = (
    "{email} is an existing account, but withdrawn (disabled and key revoked). "
    "To re-enrol, delete the account or add a key by hand; sql/accounts.sql has both."
)


def _already_enrolled(engine, email: str, table: str) -> str:
    """The sentence for a duplicate, which depends on the row it collided with.

    A second read, after the insert has already been refused, and its only job is
    the wording. Any failure here falls back to the shorter sentence rather than
    raising: a diagnostic that masks the refusal it was meant to explain would
    turn "already enrolled" into an unrelated database error.
    """
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            conn.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))
            row = conn.execute(text(_DISABLED.format(table=table)), {"email": email}).first()
    except Exception:  # noqa: BLE001 - the refusal matters, the wording is a bonus
        return f"{email} is already enrolled"
    if row is not None and row.disabled:
        return WITHDRAWN_ALREADY.format(email=email)
    return f"{email} is already enrolled"


def insert(
    engine,
    email: str,
    role: Role,
    key: str,
    key_hash: str | None = None,
    *,
    table: str = DEFAULT_TABLE,
) -> Account:
    """Enrol one account. Raises `AlreadyEnrolled` if the address already has a row.

    The row's own spelling of the address is what goes in, unfolded but
    **trimmed**: `lookup` folds when it matches, so the operator's capitalisation
    is preserved for display without affecting who is found, while surrounding
    whitespace is removed because nothing downstream can match through it
    (`usable`). An address that is odd in any other way is refused with
    `UnusableAddress` and nothing is written. Any failure that is not a duplicate
    raises as itself -- an unreachable database, a missing table and a refused
    password are all things the operator has to see, and this is a command they
    are watching rather than a page they are reading.

    `key_hash` is OpenRouter's handle for the credential, and storing it is what
    makes the account withdrawable: the Management API deletes a key by its hash,
    which is returned once, at creation. It is optional because this module is
    older than the column and because an account may be enrolled with no
    credential at all -- a row with a key and no hash is one only the OpenRouter
    dashboard can withdraw, and `withdraw` says so rather than guessing.

    Under the trail store's statement timeout, so a hung database refuses in two
    seconds rather than never.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    email = usable(email)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))
            conn.execute(
                text(_INSERT.format(table=table)),
                {
                    "email": email,
                    "role": Role(role).value,
                    "key": key,
                    "key_hash": key_hash,
                },
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
        raise AlreadyEnrolled(_already_enrolled(engine, email, table)) from exc
    return Account(email=email, role=Role(role), openrouter_key=key or None)
