"""Enrolment is read from one row, and an unreadable table enrols nobody.

The engine double here fails in the place `lookup` reads -- opening the
transaction, or executing the select -- rather than being a single always-raising
stub, for the reason `test_trail_store.py` gives at length. The test that matters
is the last of the four the task names: an engine that raises must produce
`EnrolmentUnavailable`, never `None`, because `None` is the answer that admits
nobody *and* tells them the wrong reason.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scinumbers_ask import trail_store
from scinumbers_ask.accounts import (
    Account,
    AlreadyEnrolled,
    EnrolmentUnavailable,
    UnusableAddress,
    disable,
    insert,
    lookup,
    usable,
)
from scinumbers_ask.permissions import Role


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Conn:
    def __init__(self, row, fail_on_execute):
        self.row = row
        self.fail_on_execute = fail_on_execute
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        if params is not None:
            self.params.append(dict(params))
        if self.fail_on_execute is not None and "select" in str(statement).lower():
            raise self.fail_on_execute
        return _Result(self.row)


class _Engine:
    """Returns one row (or none) for the select, or fails where told to.

    Not `conftest.RecordingEngine`: that one records writes, and this one has to
    *answer* a SELECT. Sharing them would mean a double that both returns rows
    and records inserts, which is two jobs and no clearer than two doubles.
    """

    def __init__(self, row=None, *, fail_on_begin=None, fail_on_execute=None):
        self.row = row
        self.fail_on_begin = fail_on_begin
        self.fail_on_execute = fail_on_execute
        self.conns: list[_Conn] = []

    def begin(self):
        if self.fail_on_begin is not None:
            raise self.fail_on_begin
        conn = _Conn(self.row, self.fail_on_execute)
        self.conns.append(conn)

        class _Ctx:
            def __enter__(self_inner):
                return conn

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()


def _row(email="tester@example.org", role="scientist", key="sk-or-v1-abc", disabled=False):
    return SimpleNamespace(email=email, role=role, openrouter_key=key, disabled=disabled)


# --- the four cases the task names --------------------------------------------


def test_an_enrolled_account_comes_back_with_its_role_and_credential():
    account = lookup(_Engine(_row()), "tester@example.org")
    assert account == Account(
        email="tester@example.org", role=Role.SCIENTIST, openrouter_key="sk-or-v1-abc"
    )


def test_the_account_carries_the_enrolled_form_of_the_email_not_the_typed_one():
    """The row's spelling is what the trail is stamped with and what query 8
    finds by. A mutant returning the argument instead of the row survived until
    this test varied the two."""
    account = lookup(_Engine(_row(email="Tester@Example.org")), "tester@example.org")
    assert account.email == "Tester@Example.org"


def test_an_absent_account_is_none():
    assert lookup(_Engine(None), "nobody@example.org") is None


def test_a_disabled_account_is_none_exactly_as_an_absent_one_is():
    """Varies the dimension the rule reads -- the `disabled` flag -- on an
    otherwise complete, well-formed row."""
    assert lookup(_Engine(_row(disabled=True)), "tester@example.org") is None


@pytest.mark.parametrize(
    "engine",
    [
        _Engine(fail_on_begin=ConnectionError("no route to host")),
        _Engine(fail_on_execute=RuntimeError('relation "accounts" does not exist')),
    ],
    ids=["cannot open a transaction", "the select fails"],
)
def test_an_unreadable_table_raises_rather_than_answering_none(engine):
    """The one that matters. `None` here would say "not enrolled" to a person who
    is, and -- if a caller ever treated `None` as a default -- admit everyone
    during an outage.

    **Two survivors live here, knowingly, and are a question rather than a gap.**
    Mutation testing (2026-09-17) rewrote the raise as `EnrolmentUnavailable(None)`
    and as `EnrolmentUnavailable(f"{type(None).__name__}: {exc}")`, and this test
    passed both times: it asserts that the door closes, which is what the spec
    states, and says nothing about what the exception carries. Both mutants keep
    the refusal and destroy the *reason* -- and the reason is the operator's only
    clue, because `web.admit` hands this exception to `trail_store.complain`,
    whose own docstring says the type and message "identify a misconfigured URL,
    an unreachable host and a refused password differently enough to act on".
    `openspec/specs/user-identity` says what the reader sees during an outage and
    nothing about what the operator is told, so there is no requirement to test
    against. Left alive deliberately rather than pinned by an assertion copied off
    the current string; whether operator diagnosability belongs in the spec is a
    decision, not something to settle by reading the code."""
    with pytest.raises(EnrolmentUnavailable):
        lookup(engine, "tester@example.org")


@pytest.mark.parametrize(
    ("failure", "clue"),
    [
        (ValueError("Could not parse SQLAlchemy URL from string 'postgres//db'"), "parse"),
        (
            ConnectionError('could not translate host name "db.example.invalid"'),
            "db.example.invalid",
        ),
        (PermissionError('password authentication failed for user "scinumbers"'), "password"),
    ],
    ids=["a misconfigured address", "an unreachable host", "a refused password"],
)
def test_the_refusal_preserves_what_could_not_be_read(failure, clue):
    """`user-identity`: the refusal preserves what could not be read, so that a
    misconfigured address, an unreachable host and a refused password are
    distinguishable to whoever runs the app.

    Two mutants kept the refusal and destroyed the reason, and nothing noticed:
    an operator then has a page saying "try again shortly" and no way to tell
    which of these three they are looking at. The parameters vary the cause
    rather than the outcome -- every one of them raises `EnrolmentUnavailable`,
    and what has to differ is what it carries.
    """
    with pytest.raises(EnrolmentUnavailable) as refused:
        lookup(_Engine(fail_on_execute=failure), "tester@example.org")

    said = str(refused.value)
    assert type(failure).__name__ in said, "the type is half of what tells them which failure it is"
    assert clue in said, "the provider's own words are the other half"
    assert refused.value.__cause__ is failure


def test_two_causes_do_not_produce_the_same_refusal():
    """Distinguishable is a claim about two refusals, and no parametrised case can
    make it: each sees one cause. This one sees both."""
    said = []
    for failure in (ConnectionError("no route to host"), PermissionError("password refused")):
        with pytest.raises(EnrolmentUnavailable) as refused:
            lookup(_Engine(fail_on_begin=failure), "tester@example.org")
        said.append(str(refused.value))
    assert said[0] != said[1]


def test_enrolment_unavailable_is_not_a_permission_error():
    """A caller catching `PermissionError` for a `Refused` must not catch this."""
    assert not issubclass(EnrolmentUnavailable, PermissionError)


# --- the row's edges ------------------------------------------------------------


def test_a_role_the_table_does_not_know_is_refused_and_reported(capsys):
    """An operator's typo must not become a grant. Refused as "not enrolled",
    with the reason on stderr where the operator will see it.

    A third survivor accepted here: mutation testing dropped the exception from
    `complain(..., exc)`, leaving `complain(..., None)`, and this passed. What is
    lost is the offending role text (`'scientst' is not a valid Role`); what
    survives -- the account and the word "role", both asserted below -- is enough
    to send the operator to the row. Tuning, not contract: `sql/accounts.sql`
    promises only that the application "says so on stderr", and an assertion on
    the wording would pin a sentence nothing requires."""
    assert lookup(_Engine(_row(role="scientst")), "tester@example.org") is None
    err = capsys.readouterr().err
    assert "tester@example.org" in err, "the operator needs to know which row to fix"
    assert "role" in err


def test_a_row_with_no_credential_is_still_enrolled():
    """Enrolled without a key is a state the page handles (it refuses asking and
    names the missing credential); it is not "not enrolled"."""
    account = lookup(_Engine(_row(key=None)), "tester@example.org")
    assert account is not None
    assert account.openrouter_key is None


def test_an_empty_credential_is_none_not_an_empty_string():
    account = lookup(_Engine(_row(key="")), "tester@example.org")
    assert account is not None and account.openrouter_key is None


# --- how it reads ----------------------------------------------------------------


def test_the_lookup_is_by_the_email_it_was_given_under_the_statement_timeout():
    engine = _Engine(_row())
    lookup(engine, "tester@example.org")
    (conn,) = engine.conns
    assert conn.params == [{"email": "tester@example.org"}]
    assert any(
        f"statement_timeout = {trail_store.STATEMENT_TIMEOUT_MS}" in s for s in conn.statements
    ), "a hung accounts table would otherwise hold sign-in open for ever"


def test_the_table_named_is_the_table_read():
    engine = _Engine(_row())
    lookup(engine, "tester@example.org", table="accounts_test")
    assert any("from accounts_test" in s for s in engine.conns[0].statements)


def test_enrolment_is_matched_without_regard_to_the_case_of_the_address():
    """The operator types the address into the table; the provider asserts its
    own spelling. An exact match tells a person who *is* enrolled that they are
    not, and sends the operator to look at a row that is plainly there."""
    engine = _Engine(_row(email="Tester@Example.org"))
    account = lookup(engine, "tester@example.org")
    assert account is not None
    assert account.email == "Tester@Example.org", "the row's spelling, not the typed one"
    statement = " ".join(engine.conns[0].statements).lower()
    assert "lower(email) = lower(" in statement


def test_the_account_hands_over_its_identity_and_not_its_credential():
    """`Account.identity` is what `allowed` reads, and mutmut never mutates it:
    it rewrites function bodies, and this one is inside a `@dataclass`. So it was
    seeded by hand (2026-09-17) instead -- `Identity(self.email, Role.ADMIN)`,
    which promotes every account silently, and an identity carrying an address
    that is not the account's. This test caught both, and the first was caught
    through the page as well by five of `test_web_driver_dev_panel.py`'s."""
    account = lookup(_Engine(_row()), "tester@example.org")
    assert account.identity.email == account.email
    assert account.identity.role is account.role
    assert "openrouter" not in repr(account.identity).lower()


# --- writing a row -------------------------------------------------------------


class _DuplicateConn:
    """Refuses the insert, then answers the select that chooses the wording.

    Two behaviours in one double because the sequence is the thing under test:
    the second read happens *after* a failed transaction, and a double that only
    raised would leave the wording branch unexecuted.
    """

    def __init__(self, error, row=None, fail_on_select=None):
        self.error = error
        self.row = row
        self.fail_on_select = fail_on_select
        self.statements: list[str] = []

    def execute(self, statement, params=None):
        text_ = str(statement).lower()
        self.statements.append(text_)
        if "insert" in text_:
            raise self.error
        if "select" in text_:
            if self.fail_on_select is not None:
                raise self.fail_on_select
            return _Result(self.row)
        return None


class _DuplicateEngine:
    def __init__(self, error, row=None, fail_on_select=None):
        self.conn = _DuplicateConn(error, row, fail_on_select)

    def begin(self):
        conn = self.conn

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *exc):
                return False

        return _Ctx()


class _WriteConn:
    """Records what was executed, and fails on the insert where told to.

    Fails on the *insert* rather than on any statement, so a test cannot pass by
    tripping the `set local statement_timeout` that precedes it -- which would
    prove the timeout is sent and nothing about the insert at all.
    """

    def __init__(self, fail_on_insert=None):
        self.fail_on_insert = fail_on_insert
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        if params is not None:
            self.params.append(dict(params))
        if self.fail_on_insert is not None and "insert" in str(statement).lower():
            raise self.fail_on_insert
        return None


class _WriteEngine:
    def __init__(self, fail_on_insert=None):
        self.conn = _WriteConn(fail_on_insert)

    def begin(self):
        engine = self

        class _Ctx:
            def __enter__(self):
                return engine.conn

            def __exit__(self, *exc):
                return False

        return _Ctx()


def _integrity_error(message: str, sqlstate: str | None = "23505"):
    """A real `IntegrityError` carrying a driver error with a SQLSTATE.

    The rule reads the *type* and then the SQLSTATE, so both have to be real
    here. A double whose `orig` has no `sqlstate` exercises the "raise as itself"
    branch while a test's name claims the duplicate one -- which is exactly what
    happened when the rule was narrowed and these tests went on asserting the
    old, wider behaviour.
    """
    from sqlalchemy.exc import IntegrityError

    driver_error = Exception(message)
    driver_error.sqlstate = sqlstate
    return IntegrityError(message, {}, driver_error)


def test_insert_writes_the_row_and_returns_the_account():
    engine = _WriteEngine()
    account = insert(engine, "New@example.org", Role.SCIENTIST, "sk-new", "hash-new")
    assert account == Account(email="New@example.org", role=Role.SCIENTIST, openrouter_key="sk-new")
    (params,) = engine.conn.params
    assert params == {
        "email": "New@example.org",
        "role": "scientist",
        "key": "sk-new",
        "key_hash": "hash-new",
    }
    assert any("statement_timeout" in s for s in engine.conn.statements)
    assert "New@example.org" in account.email, "the operator's own spelling is kept"


def test_insert_refuses_an_address_that_already_has_a_row():
    engine = _WriteEngine(fail_on_insert=_integrity_error("duplicate key accounts_email_lower"))
    with pytest.raises(AlreadyEnrolled) as refused:
        insert(engine, "tester@example.org", Role.STUDENT, "sk-dup")
    assert "tester@example.org" in str(refused.value)


def test_insert_refuses_an_exact_repeat_too():
    """The primary key catches the exact repeat and the index catches the
    case-only one. Both mean "already enrolled", and `insert` does not read the
    constraint's name to tell them apart -- a rule that would go quietly false
    the day the index is renamed."""
    engine = _WriteEngine(fail_on_insert=_integrity_error('duplicate key value "accounts_pkey"'))
    with pytest.raises(AlreadyEnrolled):
        insert(engine, "tester@example.org", Role.STUDENT, "sk-dup")


def test_an_integrity_error_that_is_not_a_duplicate_raises_as_itself():
    """Against today's schema only the primary key and `accounts_email_lower` can
    fire, so "every IntegrityError means already enrolled" is right -- and wrong
    the day a `check` on `role` arrives, when the operator is sent looking for a
    row that is not there while the freshly minted key is silently withdrawn.
    The negative case varies the SQLSTATE, which is what the rule reads."""
    engine = _WriteEngine(
        fail_on_insert=_integrity_error("new row violates check constraint", sqlstate="23514")
    )
    with pytest.raises(Exception) as failed:
        insert(engine, "new@example.org", Role.STUDENT, "sk-new")
    assert not isinstance(failed.value, AlreadyEnrolled)


def test_insert_lets_any_other_failure_raise_as_itself():
    """Not `AlreadyEnrolled`: an unreachable database and a missing table are
    things the operator has to see, and reporting them as a duplicate would send
    them to look at a row that is not there."""
    engine = _WriteEngine(fail_on_insert=RuntimeError('relation "accounts" does not exist'))
    with pytest.raises(RuntimeError) as failed:
        insert(engine, "new@example.org", Role.STUDENT, "sk-new")
    assert not isinstance(failed.value, AlreadyEnrolled)


# --- an address nothing could match -------------------------------------------------


@pytest.mark.parametrize(
    "typed",
    [
        "tester@example.org\n",
        " tester@example.org",
        "tester@example.org\t",
        "\ntester@example.org ",
    ],
    ids=["trailing newline", "leading space", "trailing tab", "both"],
)
def test_surrounding_whitespace_is_trimmed_rather_than_refused(typed):
    """The operator's tool, not their intent: a heredoc adds the newline and a
    pasted line adds the spaces. Trimming costs nothing and refusing would cost
    the operator a second attempt over a character they cannot see."""
    assert usable(typed) == "tester@example.org"


@pytest.mark.parametrize(
    "typed",
    ["tes ter@example.org", "tester@exa\tmple.org", "tester@example.org x"],
    ids=["a space in the name", "a tab in the domain", "a second word"],
)
def test_whitespace_inside_an_address_is_refused_rather_than_removed(typed):
    """The asymmetry is the decision. Removing it would enrol an address the
    operator did not type, and no provider would assert either form."""
    with pytest.raises(UnusableAddress):
        usable(typed)


def test_a_control_character_is_refused_even_where_it_is_not_whitespace():
    """`'\\x00'.isspace()` is False, so the whitespace rule alone lets it through
    -- and a NUL in a primary key is a row no claim can ever match."""
    with pytest.raises(UnusableAddress):
        usable("tester@exam\x00ple.org")


@pytest.mark.parametrize("typed", ["", "   ", "\n"], ids=["empty", "spaces", "newline"])
def test_an_address_that_is_only_whitespace_is_refused(typed):
    with pytest.raises(UnusableAddress):
        usable(typed)


@pytest.mark.parametrize(
    "typed",
    ["tester", "@example.org", "tester@"],
    ids=["no @ at all", "no name", "no domain"],
)
def test_something_that_is_not_an_address_is_refused(typed):
    with pytest.raises(UnusableAddress):
        usable(typed)


def test_the_refusal_shows_the_character_that_cannot_be_seen():
    """`repr`, not the bare string. An error naming `tester@example.org` when the
    address ends in a newline tells the operator what they already believe."""
    with pytest.raises(UnusableAddress) as refused:
        usable("tes ter@example.org")
    assert "\\n" in str(refused.value) or "'tes ter@example.org'" in str(refused.value)


def test_insert_stores_the_trimmed_address_not_the_typed_one():
    """The row is what every later claim is matched against, so this is the write
    that decides whether the account can ever be used."""
    engine = _WriteEngine()
    account = insert(engine, "New@example.org\n", Role.SCIENTIST, "sk-new")
    (params,) = engine.conn.params
    assert params["email"] == "New@example.org", "the newline reached the row"
    assert account.email == "New@example.org"


def test_insert_refuses_an_unusable_address_and_writes_nothing():
    """Before the connection is opened, so there is nothing to compensate for."""
    engine = _WriteEngine()
    with pytest.raises(UnusableAddress):
        insert(engine, "new user@example.org", Role.SCIENTIST, "sk-new")
    assert engine.conn.params == [], "a row was written for an address nothing can match"


def test_a_claim_is_trimmed_before_it_is_matched():
    """The other direction of the same rule. A provider will not send whitespace,
    but the rule having one home is what keeps the two directions in step."""
    engine = _Engine(_row())
    assert lookup(engine, " tester@example.org\n") is not None
    (params,) = engine.conns[0].params
    assert params == {"email": "tester@example.org"}


def test_a_claim_that_cannot_be_matched_is_not_enrolled_rather_than_an_error():
    """Fails closed into a door that already exists. Raising here would take the
    page down; inventing a new sentence would be a refusal for a case no provider
    produces."""
    engine = _Engine(_row())
    assert lookup(engine, "not an address") is None
    assert engine.conns == [], "the database was asked about an address it cannot hold"


# --- withdrawing one account --------------------------------------------------------


class _DisableConn:
    """Answers the `update ... returning` with the row it was given, or none."""

    def __init__(self, row):
        self.row = row
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        if params is not None:
            self.params.append(dict(params))
        return _Result(self.row if "update" in str(statement).lower() else None)


class _DisableEngine:
    def __init__(self, row=None):
        self.conn = _DisableConn(row)

    def begin(self):
        conn = self.conn

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *exc):
                return False

        return _Ctx()


def _withdrawn_row(email="tester@example.org", key_hash="hash-abc"):
    return SimpleNamespace(email=email, openrouter_key_hash=key_hash)


def test_disabling_returns_the_handle_that_can_withdraw_the_credential():
    """One statement, so the row cannot be read and then found changed -- and the
    handle has to come back from it, because nothing else in the system knows it."""
    engine = _DisableEngine(_withdrawn_row())
    withdrawn = disable(engine, "tester@example.org")
    assert withdrawn.email == "tester@example.org"
    assert withdrawn.key_hash == "hash-abc"
    statement = " ".join(engine.conn.statements).lower()
    assert "disabled = true" in statement and "returning" in statement
    assert any("statement_timeout" in s for s in engine.conn.statements)


def test_disabling_an_account_that_is_not_there_is_none():
    """Most often the address is right and the branch is wrong, so the caller has
    to be able to say that rather than report a withdrawal that did not happen."""
    assert disable(_DisableEngine(None), "nobody@example.org") is None


def test_an_account_with_no_handle_comes_back_disabled_and_unwithdrawable():
    """A row enrolled before the handle was stored. The two halves are separable
    on purpose: refusing the reader works, revoking their key does not, and the
    caller must be able to tell them apart to say so."""
    withdrawn = disable(_DisableEngine(_withdrawn_row(key_hash=None)), "old@example.org")
    assert withdrawn is not None
    assert withdrawn.key_hash is None


def test_the_address_is_matched_without_regard_to_case_here_too():
    engine = _DisableEngine(_withdrawn_row())
    disable(engine, "Tester@Example.org")
    assert "lower(email) = lower(" in " ".join(engine.conn.statements).lower()
    (params,) = engine.conn.params
    assert params == {"email": "Tester@Example.org"}


def test_disabling_is_unconditional_so_a_hand_disabled_row_still_yields_its_handle():
    """The case a withdrawal command exists for: an account someone disabled by
    hand whose key was never revoked. A `where ... and not disabled` would report
    "no such account" for a row plainly there, and the live key would stay live."""
    engine = _DisableEngine(_withdrawn_row())
    assert disable(engine, "tester@example.org").key_hash == "hash-abc"
    assert "not disabled" not in " ".join(engine.conn.statements).lower()


# --- which duplicate it is ----------------------------------------------------------


def test_a_duplicate_of_a_withdrawn_row_reads_as_withdrawn_not_as_active():
    """ "Already enrolled" is true of a withdrawn row and reads as "this person has
    access", which is the opposite. The operator's next step differs too: there is
    nothing to reconsider, there is a row to clear."""
    engine = _DuplicateEngine(_integrity_error("duplicate key"), row=SimpleNamespace(disabled=True))
    with pytest.raises(AlreadyEnrolled) as refused:
        insert(engine, "gone@example.org", Role.STUDENT, "sk-new", "hash-new")
    said = str(refused.value)
    assert "withdrawn" in said
    assert "sql/accounts.sql" in said, "the operator is told it is refused and not what to do"


def test_a_duplicate_of_a_live_row_still_says_already_enrolled():
    """The negative case varies the dimension the rule reads -- the `disabled`
    flag on the row it collided with -- rather than the shape of the failure."""
    engine = _DuplicateEngine(
        _integrity_error("duplicate key"), row=SimpleNamespace(disabled=False)
    )
    with pytest.raises(AlreadyEnrolled) as refused:
        insert(engine, "live@example.org", Role.STUDENT, "sk-new", "hash-new")
    assert str(refused.value) == "live@example.org is already enrolled"


def test_the_wording_read_never_masks_the_refusal_it_explains():
    """A diagnostic that raises would turn "already enrolled" into an unrelated
    database error, and the operator would go looking for an outage."""
    engine = _DuplicateEngine(
        _integrity_error("duplicate key"), fail_on_select=ConnectionError("no route to host")
    )
    with pytest.raises(AlreadyEnrolled) as refused:
        insert(engine, "live@example.org", Role.STUDENT, "sk-new", "hash-new")
    assert "already enrolled" in str(refused.value)
