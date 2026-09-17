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
from scinumbers_ask.accounts import Account, EnrolmentUnavailable, lookup
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
