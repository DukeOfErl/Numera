"""Enrolling one tester: the guards, and what a half-done enrolment leaves behind.

Every refusal is asserted on **what was not done** as well as on the exception:
`Uncapped` with the opener never called, `AlreadyEnrolled` with a `DELETE` sent.
An exception alone would pass for an implementation that minted first and threw
afterwards, which is the failure this module is arranged to prevent.

The opener double records every request, so "the credential was withdrawn" is a
claim about a `DELETE` that was actually sent and not about a branch that was
reached. It fails where it is told to, by method and URL, rather than always --
a double that raises on everything cannot tell the mint's failure from the
revoke's, and those are two different outcomes for the operator.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from scinumbers_ask import accounts, neon
from scinumbers_ask import enrol as enrol_mod
from scinumbers_ask.accounts import Account, AlreadyEnrolled
from scinumbers_ask.enrol import (
    CredentialNotWithdrawn,
    KeyLeftBehind,
    MintFailed,
    NotEnrolled,
    NothingEnrolled,
    Uncapped,
    enrol,
    main,
    mint,
    revoke,
    withdraw,
    withdraw_main,
)
from scinumbers_ask.permissions import Role

HASH = "abc123hash"
KEY = "sk-or-v1-secret"


class _Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Opener:
    """Answers by (method, url-fragment), and records what it was asked.

    **Headers and the timeout are recorded, not only the method and the URL.**
    Mutation testing replaced `management_key` with `None` in every call in this
    module -- and deleted the `Authorization` header outright -- and the whole
    suite stayed green, because this double checked the shape of a request and
    never its credential. In reality each of those calls would be refused with a
    401. A double that does not look at what a test claims cannot fail for the
    reason the test is named after.
    """

    def __init__(self, routes=None, fail=None):
        self.routes = routes or {}
        self.fail = fail or {}
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[dict] = []
        self.headers: list[dict] = []
        self.timeouts: list = []

    def __call__(self, request, timeout=None):
        # `get_method()`, not `.method`: urllib only sets the attribute when the
        # caller passed one, so a GET built without it has no such attribute.
        method, url = request.get_method(), request.full_url
        self.calls.append((method, url))
        presented = {k.lower(): v for k, v in request.header_items()}.get("authorization")
        if presented in (None, "Bearer None", "Bearer "):
            # What OpenRouter does, rather than what is convenient. Mutation
            # testing put `None` in place of the management key at six call
            # sites -- including all four compensating revokes, where
            # `_revoke_quietly` swallows the failure -- and every one survived,
            # because this double answered any request that had the right shape.
            # Refusing here kills them all at once and keeps the assertion where
            # it belongs: in the double's behaviour, not repeated in eight tests.
            raise urllib.error.HTTPError(url, 401, "No auth credentials found", {}, None)
        # urllib title-cases header names it is given, so read them back the way
        # it stores them rather than the way the source spells them.
        self.headers.append(dict(request.header_items()))
        self.timeouts.append(timeout)
        if request.data:
            self.bodies.append(json.loads(request.data.decode("utf-8")))

        for fragment, error in self.fail.items():
            if fragment in f"{method} {url}":
                raise error
        for fragment, payload in self.routes.items():
            if fragment in f"{method} {url}":
                return _Response(payload)
        return _Response({})

    def authorisations(self):
        """What each call presented as its credential, in order."""
        return [
            {k.lower(): v for k, v in headers.items()}.get("authorization")
            for headers in self.headers
        ]

    def methods(self):
        return [method for method, _ in self.calls]


def _minted(limit=5.0, reset="monthly"):
    return {"key": KEY, "data": {"hash": HASH, "limit": limit, "limit_reset": reset}}


class _Engine:
    """Inserts, or fails where told. Not a database: `test_accounts.py` covers that."""

    def __init__(self, error=None):
        self.error = error
        self.inserted: list[tuple] = []

    def insert(self, email, role, key, key_hash=None):
        if self.error is not None:
            raise self.error
        self.inserted.append((email, role, key, key_hash))
        return Account(email=email, role=role, openrouter_key=key)


@pytest.fixture
def engine(monkeypatch):
    built = _Engine()

    def insert(engine_, email, role, key, key_hash=None, **kwargs):
        return engine_.insert(email, role, key, key_hash)

    monkeypatch.setattr(accounts, "insert", insert)
    monkeypatch.setattr(enrol_mod.accounts, "insert", insert)
    return built


# --- refused before anything is issued ---------------------------------------------


@pytest.mark.parametrize("cap", [0, -1, 0.0, None])
def test_a_credential_is_never_issued_without_a_cap(engine, cap):
    """The opener is never called, which is the assertion that matters: an
    exception raised *after* minting would satisfy `pytest.raises` and still have
    created the uncapped key ADR-0780's reasoning forbids."""
    opener = _Opener()
    with pytest.raises(Uncapped):
        enrol(engine, "mgmt", "new@example.org", Role.SCIENTIST, cap, opener=opener)
    assert opener.calls == [], "something was called before the cap was checked"
    assert engine.inserted == []


def test_a_role_that_is_not_a_role_is_refused_before_minting(engine):
    opener = _Opener()
    with pytest.raises(ValueError) as refused:
        enrol(engine, "mgmt", "new@example.org", "professor", 5, opener=opener)
    assert "professor" in str(refused.value)
    assert opener.calls == []


def test_an_address_nothing_could_match_is_refused_before_minting(engine):
    """Leaving this to `insert` would work -- the compensating revoke withdraws
    the key -- but it spends a live call on both ends to learn what a string
    could have said, and the operator reads a sentence about withdrawal rather
    than about their typo."""
    opener = _Opener()
    with pytest.raises(accounts.UnusableAddress) as refused:
        enrol(engine, "mgmt", "new user@example.org", Role.SCIENTIST, 5, opener=opener)
    assert "new user@example.org" in str(refused.value)
    assert opener.calls == [], "a credential was minted for an address with no row to hold it"
    assert engine.inserted == []


def test_the_key_is_minted_under_the_address_the_row_will_carry(engine):
    """The name is how the operator finds the key at OpenRouter to withdraw it.
    Minted under the untrimmed address and stored under the trimmed one, it is
    findable by an address that matches nothing in the table."""
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": _minted()})
    account = enrol(engine, "mgmt", " new@example.org\n", Role.SCIENTIST, 5, opener=opener)
    assert account.email == "new@example.org"
    (minting,) = [body for body in opener.bodies if "name" in body]
    assert minting["name"] == "new@example.org"


# --- the happy path ----------------------------------------------------------------


def test_every_call_to_the_provider_presents_the_management_key(engine):
    """Mutation testing put `None` in place of the management key in all four
    call sites -- the mint, the patch, the revoke and the cleanup revoke -- and
    nothing failed. Each of those would be a 401 against the real provider: the
    key is minted, and then neither withdrawn nor recorded, which is the one
    outcome this module is arranged to avoid."""
    opener = _Opener(
        {
            "POST https://openrouter.ai/api/v1/keys": _minted(reset=None),
            "PATCH": {"data": {"hash": HASH, "limit": 5.0, "limit_reset": "monthly"}},
        }
    )
    mint("mgmt-secret", name="new@example.org", limit_usd=5, opener=opener)
    assert opener.authorisations() == ["Bearer mgmt-secret", "Bearer mgmt-secret"]
    assert all(t is not None for t in opener.timeouts), (
        "an operator waiting at a prompt has to meet a failure, not a hang"
    )

    withdrawing = _Opener()
    revoke("mgmt-secret", HASH, opener=withdrawing)
    assert withdrawing.authorisations() == ["Bearer mgmt-secret"]


def test_the_cleanup_revoke_presents_the_key_and_names_the_credential():
    """The compensating call is the one nobody watches, and an unauthenticated
    one fails silently by design -- `_revoke_quietly` swallows it."""
    opener = _Opener(
        {"POST https://openrouter.ai/api/v1/keys": _minted(limit=1000)},
    )
    with pytest.raises(MintFailed):
        mint("mgmt-secret", name="new@example.org", limit_usd=5, opener=opener)
    deletes = [
        (url, auth)
        for (method, url), auth in zip(opener.calls, opener.authorisations(), strict=True)
        if method == "DELETE"
    ]
    assert deletes == [(f"https://openrouter.ai/api/v1/keys/{HASH}", "Bearer mgmt-secret")]


def test_a_cap_below_a_dollar_is_still_a_cap(engine):
    """The spec refuses "no cap or a cap that is not positive", so the boundary
    is zero and not one. `limit_usd > 0` could be widened to `> 1` with nothing
    failing, which would have refused a 50-cent tester for no stated reason --
    and the assertion here comes from that requirement, not from running the
    code."""
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": _minted(limit=0.5)})
    account = enrol(engine, "mgmt", "new@example.org", Role.STUDENT, 0.5, opener=opener)
    assert account.openrouter_key == KEY
    assert opener.bodies[0]["limit"] == 0.5


def test_enrolling_mints_a_capped_key_and_records_the_account(engine):
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": _minted()})
    account = enrol(engine, "mgmt", "new@example.org", Role.SCIENTIST, 5, opener=opener)
    assert account.openrouter_key == KEY
    assert engine.inserted == [("new@example.org", Role.SCIENTIST, KEY, HASH)], (
        "the handle is stored beside the key, and it is the only thing that can withdraw it"
    )
    (body,) = opener.bodies
    assert body == {"name": "new@example.org", "limit": 5, "limit_reset": "monthly"}
    assert "DELETE" not in opener.methods(), "nothing to undo on the path that worked"


# --- the echo ----------------------------------------------------------------------


def test_a_cap_that_comes_back_wrong_is_revoked_and_refused():
    """Not retried. A provider that disagrees about the number is not one to
    argue with, and the key it made is not one to hand out."""
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": _minted(limit=1000)})
    with pytest.raises(MintFailed) as refused:
        mint("mgmt", name="new@example.org", limit_usd=5, opener=opener)
    assert "1000" in str(refused.value)
    assert ("DELETE", f"https://openrouter.ai/api/v1/keys/{HASH}") in opener.calls


def test_a_reset_that_comes_back_wrong_is_patched_once_and_then_accepted():
    opener = _Opener(
        {
            "POST https://openrouter.ai/api/v1/keys": _minted(reset=None),
            "PATCH": {"data": {"hash": HASH, "limit": 5.0, "limit_reset": "monthly"}},
        }
    )
    minted = mint("mgmt", name="new@example.org", limit_usd=5, opener=opener)
    assert minted.key == KEY
    assert opener.methods() == ["POST", "PATCH"], "exactly one retry"
    assert "DELETE" not in opener.methods()


def test_a_reset_the_patch_cannot_fix_is_revoked_and_refused(capsys):
    opener = _Opener(
        {
            "POST https://openrouter.ai/api/v1/keys": _minted(reset=None),
            "PATCH": {"data": {"hash": HASH, "limit": 5.0, "limit_reset": None}},
        }
    )
    with pytest.raises(MintFailed):
        mint("mgmt", name="new@example.org", limit_usd=5, opener=opener)
    assert opener.methods() == ["POST", "PATCH", "DELETE"]
    _withdrew_cleanly(capsys)


def test_a_cap_echoed_as_a_string_is_the_same_cap():
    """`_same_amount` exists to compare across JSON's number types, and strict
    equality survived the whole suite until this test: `5 == 5.0` is True in
    Python, so an int/float fixture cannot tell the two implementations apart.
    A provider echoing `"5"` can."""
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": _minted(limit="5")})
    assert mint("mgmt", name="new@example.org", limit_usd=5, opener=opener).key == KEY
    assert "DELETE" not in opener.methods()


def test_a_cap_echoed_as_something_that_is_not_a_number_is_refused():
    """The other half of the same rule: unreadable is not "close enough". An
    echo that cannot be compared is an uncapped key as far as this command can
    tell, and ADR-0780's reasoning does not survive one of those."""
    for echoed in ("unlimited", None, {}):
        opener = _Opener({"POST https://openrouter.ai/api/v1/keys": _minted(limit=echoed)})
        with pytest.raises(MintFailed):
            mint("mgmt", name="new@example.org", limit_usd=5, opener=opener)
        assert "DELETE" in opener.methods(), echoed


def test_a_cleanup_that_fails_does_not_replace_the_reason_it_was_cleaning_up(capsys):
    """`_revoke_quietly`'s docstring claims the original failure is the one the
    operator reads and the hash still reaches stderr. Nothing executed that
    branch until this test, so the sentence had no artifact behind it."""
    opener = _Opener(
        {"POST https://openrouter.ai/api/v1/keys": _minted(limit=1000)},
        fail={"DELETE": RuntimeError("openrouter is down")},
    )
    with pytest.raises(MintFailed) as refused:
        mint("mgmt", name="new@example.org", limit_usd=5, opener=opener)
    assert "1000" in str(refused.value), "the cleanup's failure replaced the real one"
    assert HASH in capsys.readouterr().err, "the loose key was not named anywhere"


def _withdrew_cleanly(capsys):
    """That the compensating revoke actually succeeded, not merely that it was attempted.

    `_revoke_quietly` swallows a failing revoke by design, so "a DELETE was sent"
    is satisfied by one the provider refused -- and the key is then live, which
    is the outcome the spec's "the credential SHALL be withdrawn" forbids.
    Mutation testing found four call sites where the credential could be dropped
    from the cleanup call with nothing failing; this is what says they went out
    authenticated.
    """
    assert "could not revoke" not in capsys.readouterr().err


def test_a_hash_with_no_key_is_withdrawn_rather_than_left_live(capsys):
    """`MintFailed` promises that anything created has been revoked, and this
    path used to break that promise while holding the handle to keep it: a capped
    credential existed at the provider and this process was the only thing that
    knew its hash."""
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": {"data": {"hash": HASH}}})
    with pytest.raises(MintFailed):
        mint("mgmt", name="new@example.org", limit_usd=5, opener=opener)
    assert ("DELETE", f"https://openrouter.ai/api/v1/keys/{HASH}") in opener.calls
    _withdrew_cleanly(capsys)


def test_a_response_with_no_hash_says_nothing_can_be_withdrawn():
    """The other half: with no handle there is nothing to revoke, so the operator
    is told to look rather than reassured by the exception's docstring."""
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": {"key": KEY}})
    with pytest.raises(MintFailed) as refused:
        mint("mgmt", name="new@example.org", limit_usd=5, opener=opener)
    assert "dashboard" in str(refused.value).lower()
    assert "DELETE" not in opener.methods(), "nothing names what to withdraw"


def test_a_patch_that_cannot_be_sent_still_withdraws_the_key(capsys):
    """The two checked failures revoke; the transport failure between them used
    to escape without doing so, leaving a live credential and no `Minted` for
    `enrol` to compensate from."""
    opener = _Opener(
        {"POST https://openrouter.ai/api/v1/keys": _minted(reset=None)},
        fail={"PATCH": RuntimeError("connection reset")},
    )
    with pytest.raises(RuntimeError):
        mint("mgmt", name="new@example.org", limit_usd=5, opener=opener)
    assert ("DELETE", f"https://openrouter.ai/api/v1/keys/{HASH}") in opener.calls
    _withdrew_cleanly(capsys)


# --- when the row cannot be written ------------------------------------------------


def test_an_address_already_enrolled_keeps_its_row_and_loses_the_new_key(monkeypatch):
    """The refusal the operator sees is the duplicate, not a generic failure --
    and the key minted a moment earlier is gone rather than left to expire."""
    engine = _Engine(error=AlreadyEnrolled("tester@example.org is already enrolled"))
    monkeypatch.setattr(enrol_mod.accounts, "insert", lambda e, *a, **k: e.insert(*a))
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": _minted()})
    with pytest.raises(AlreadyEnrolled):
        enrol(engine, "mgmt", "tester@example.org", Role.STUDENT, 5, opener=opener)
    assert ("DELETE", f"https://openrouter.ai/api/v1/keys/{HASH}") in opener.calls


def test_a_row_that_cannot_be_written_withdraws_the_credential(monkeypatch):
    engine = _Engine(error=RuntimeError("could not connect"))
    monkeypatch.setattr(enrol_mod.accounts, "insert", lambda e, *a, **k: e.insert(*a))
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": _minted()})
    with pytest.raises(NothingEnrolled):
        enrol(engine, "mgmt", "new@example.org", Role.STUDENT, 5, opener=opener)
    assert ("DELETE", f"https://openrouter.ai/api/v1/keys/{HASH}") in opener.calls


def test_a_credential_that_cannot_be_withdrawn_is_named(monkeypatch):
    """The one outcome that leaves work for a person, so the hash has to be in
    the sentence: without it the operator knows a key is loose and not which."""
    engine = _Engine(error=RuntimeError("could not connect"))
    monkeypatch.setattr(enrol_mod.accounts, "insert", lambda e, *a, **k: e.insert(*a))
    opener = _Opener(
        {"POST https://openrouter.ai/api/v1/keys": _minted()},
        fail={"DELETE": RuntimeError("openrouter is down")},
    )
    with pytest.raises(KeyLeftBehind) as left:
        enrol(engine, "mgmt", "new@example.org", Role.STUDENT, 5, opener=opener)
    assert HASH in str(left.value)
    assert KEY not in str(left.value), "the hash names the key; the key itself is not printed"


# --- the operator's own credentials ------------------------------------------------


def _http(code: int):
    return urllib.error.HTTPError("https://x", code, "refused", {}, None)


def test_a_refused_management_key_says_so_and_says_what_to_do():
    """An expiring management key is a failure mode chosen deliberately, so it
    gets a sentence rather than `HTTP Error 401`. The distinction matters because
    the operator's next move -- mint a new management key -- is nothing like
    their next move for any other failure here."""
    opener = _Opener(fail={"POST": _http(401)})
    with pytest.raises(enrol_mod.CredentialRefused) as refused:
        mint("expired", name="new@example.org", limit_usd=5, opener=opener)
    said = str(refused.value)
    assert "management key" in said
    assert "openrouter.ai/settings/management-keys" in said
    assert "nothing was enrolled" in said
    # The one consequence an operator will not guess: the same key withdraws
    # credentials, so that stops working too while it is refused.
    assert "withdrawing" in said and "dashboard" in said


@pytest.mark.parametrize("code", [429, 500, 502, 503])
def test_a_provider_problem_is_not_reported_as_an_expired_key(code):
    """The negative case varies **the status code**, which is what the rule
    reads -- not merely the outcome. A 502 reported as an expired key sends the
    operator to mint a replacement for a key that is fine, and the same shape of
    mistake has been made in this repository before (see `.claude/rules/
    testing.md` on `_is_out_of_credit`)."""
    opener = _Opener(fail={"POST": _http(code)})
    with pytest.raises(urllib.error.HTTPError):
        mint("fine", name="new@example.org", limit_usd=5, opener=opener)


def test_a_refused_key_is_reported_from_the_revoke_too():
    """The compensating revoke is the call nobody watches, and it uses the same
    credential. The guard is in `_post`, which all three calls pass through, so
    this holds without a second rule."""
    opener = _Opener(fail={"DELETE": _http(401)})
    with pytest.raises(enrol_mod.CredentialRefused):
        revoke("expired", HASH, opener=opener)


def test_a_refused_neon_key_says_so_and_does_not_blame_the_branch():
    """`BranchNotFound` lists the branches it found, which is the wrong help
    entirely when the answer is that none could be read."""
    opener = _Opener(fail={"branches": _http(401)})
    with pytest.raises(neon.ApiKeyRefused) as refused:
        neon.branch_id("expired", "proj", "alpha", opener=opener)
    said = str(refused.value)
    assert "NEON_API_KEY" in said and "NEON_PROJECT_ID" in said
    assert "alpha" not in said, "a refused key is not a wrong branch name"


@pytest.mark.parametrize("code", [429, 500, 503])
def test_a_neon_outage_is_not_reported_as_an_expired_key(code):
    opener = _Opener(fail={"branches": _http(code)})
    with pytest.raises(urllib.error.HTTPError):
        neon.branch_id("fine", "proj", "alpha", opener=opener)


def test_the_command_reports_a_refused_credential_as_one_sentence(monkeypatch, capsys):
    """Through `main`, because that is where the operator meets it."""
    _env(monkeypatch)

    def refusing(*a, **k):
        raise neon.ApiKeyRefused(neon.API_KEY_REFUSED)

    monkeypatch.setattr(neon, "branch_id", refusing)
    argv = ["new@example.org", "scientist", "--limit-usd", "5", "--branch", "alpha"]
    assert main(argv) == 1
    out = capsys.readouterr()
    assert "NEON_API_KEY" in out.err
    assert out.out == "", "a refusal printed on the success channel"


# --- resolving the branch ----------------------------------------------------------


def _branches(*names):
    return {"branches": [{"id": f"br-{n}", "name": n} for n in names]}


def test_the_branch_is_matched_exactly_among_partial_hits():
    """Neon's `search` is a partial match, so `alpha` also returns `alpha-2`.
    Taking the first would enrol a tester into whichever branch Neon listed
    first, which is the silent wrong write this path exists to prevent."""
    opener = _Opener({"branches": _branches("alpha-2", "alpha", "alpha-old")})
    assert neon.branch_id("napi", "proj", "alpha", opener=opener) == "br-alpha"


def test_a_branch_that_does_not_exist_is_refused_with_what_does():
    opener = _Opener({"branches": _branches("alpha", "alpha-2")})
    with pytest.raises(neon.BranchNotFound) as refused:
        neon.branch_id("napi", "proj", "alfa", opener=opener)
    assert "alpha" in str(refused.value) and "alpha-2" in str(refused.value)


def test_no_branches_at_all_is_refused():
    opener = _Opener({"branches": {"branches": []}})
    with pytest.raises(neon.BranchNotFound) as refused:
        neon.branch_id("napi", "proj", "alpha", opener=opener)
    assert "none" in str(refused.value)


def test_two_branches_of_the_same_name_are_refused():
    """Neon will not produce this; the rule is "exactly one" rather than "the
    first one" so that it cannot, and so the refusal is testable."""
    opener = _Opener(
        {"branches": {"branches": [{"id": "br-1", "name": "x"}, {"id": "br-2", "name": "x"}]}}
    )
    with pytest.raises(neon.BranchNotFound):
        neon.branch_id("napi", "proj", "x", opener=opener)


def test_the_connection_url_is_pooled_and_renamed_for_psycopg():
    opener = _Opener(
        {
            "connection_uri": {
                "uri": "postgresql://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require"
            }
        }
    )
    url = neon.connection_url("napi", "proj", "br-alpha", opener=opener)
    assert url.startswith("postgresql+psycopg://"), "SQLAlchemy would reach for psycopg2"
    assert "-pooler." in url, "the direct endpoint is not for a rerun-shaped workload"
    assert "sslmode=require" in url
    (_, asked) = opener.calls[0]
    assert "pooled=true" in asked and "branch_id=br-alpha" in asked


def test_the_database_and_role_reach_the_request(monkeypatch):
    """Mutation testing deleted `database_name` and renamed `role_name`, and
    nothing failed: the URL assertions covered `pooled` and `branch_id` only. A
    dropped `role_name` asks Neon for its default role, so the command would hand
    back a connection URL for a role the operator did not choose — and the insert
    would fail, or worse succeed, somewhere else entirely."""
    opener = _Opener({"connection_uri": {"uri": "postgresql://u:p@h-pooler.x/db"}})
    neon.connection_url("napi", "proj", "br-alpha", opener=opener)
    (_, asked) = opener.calls[0]
    assert "database_name=neondb" in asked and "role_name=neondb_owner" in asked

    other = _Opener({"connection_uri": {"uri": "postgresql://u:p@h-pooler.x/db"}})
    neon.connection_url("napi", "proj", "br-alpha", database="other", role="reader", opener=other)
    (_, asked) = other.calls[0]
    assert "database_name=other" in asked and "role_name=reader" in asked


def test_both_control_plane_calls_carry_a_timeout():
    """An operator waiting at a prompt has to meet a failure rather than a hang,
    and mutation testing showed the timeout could be dropped or set to `None` with
    nothing failing — in `neon.py` as in `enrol.py`, where the same gap was found
    and closed first."""
    branches = _Opener({"branches": _branches("alpha")})
    neon.branch_id("napi", "proj", "alpha", opener=branches)
    uri = _Opener({"connection_uri": {"uri": "postgresql://u:p@h-pooler.x/db"}})
    neon.connection_url("napi", "proj", "br-alpha", opener=uri)
    for opener in (branches, uri):
        assert opener.timeouts and all(t is not None for t in opener.timeouts)


def test_a_response_with_no_uri_is_an_error():
    opener = _Opener({"connection_uri": {}})
    with pytest.raises(RuntimeError):
        neon.connection_url("napi", "proj", "br-alpha", opener=opener)


# --- the command -------------------------------------------------------------------


def _env(monkeypatch, **overrides):
    values = {
        "OPENROUTER_MANAGEMENT_KEY": "mgmt",
        "NEON_API_KEY": "napi",
        "NEON_PROJECT_ID": "proj",
    }
    values.update(overrides)
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def test_the_command_refuses_without_a_branch_and_says_why(monkeypatch, capsys):
    """argparse's own "required" says nothing about why, and this is the mistake
    whose symptom appears somewhere else: the tester is told they are not
    enrolled while the operator is looking at their row."""
    _env(monkeypatch)
    called: list = []
    # Every outbound path, not only the two the guard is expected to reach
    # first. A verifier deleted the guard and this test's own doubles let the
    # run out to the real `console.neon.tech` -- an unmarked test making a live
    # call, and an assertion that read as "nothing happened" while not covering
    # the call that did. The double has to be as wide as the claim.
    monkeypatch.setattr(neon, "branch_id", lambda *a, **k: called.append(("branch_id", a)))
    monkeypatch.setattr(
        neon, "connection_url", lambda *a, **k: called.append(("connection_url", a))
    )
    monkeypatch.setattr(
        enrol_mod.trail_store, "engine_from_url", lambda *a, **k: called.append(("engine", a))
    )
    monkeypatch.setattr(enrol_mod, "enrol", lambda *a, **k: called.append(("enrol", a)))
    assert main(["new@example.org", "scientist", "--limit-usd", "5"]) == 2
    said = capsys.readouterr().err
    assert "none is assumed" in said and "--branch" in said
    assert called == [], "a branch was resolved or a key minted without one named"


@pytest.mark.parametrize(
    "missing", ["OPENROUTER_MANAGEMENT_KEY", "NEON_API_KEY", "NEON_PROJECT_ID"]
)
def test_the_command_names_the_variable_that_is_missing(monkeypatch, capsys, missing):
    _env(monkeypatch, **{missing: None})
    called: list = []
    monkeypatch.setattr(neon, "branch_id", lambda *a, **k: called.append(a))
    argv = ["new@example.org", "scientist", "--limit-usd", "5", "--branch", "alpha"]
    assert main(argv) == 2
    assert missing in capsys.readouterr().err
    assert called == []


@pytest.mark.parametrize("cap", ["0", "-1"])
def test_a_bad_cap_costs_no_live_call(monkeypatch, capsys, cap):
    """The guard belongs to the operation and `enrol` still runs it -- but if the
    command only met it there, `--limit-usd 0` would spend two live control-plane
    calls before anything said no."""
    _env(monkeypatch)
    reached: list = []
    monkeypatch.setattr(neon, "branch_id", lambda *a, **k: reached.append(a))
    monkeypatch.setattr(neon, "connection_url", lambda *a, **k: reached.append(a))
    argv = ["new@example.org", "scientist", "--limit-usd", cap, "--branch", "alpha"]
    assert main(argv) == 1
    assert "not a cap" in capsys.readouterr().err
    assert reached == [], "a live call was made for a cap that was never going to pass"


def test_an_unknown_branch_costs_nothing(monkeypatch, capsys):
    _env(monkeypatch)
    minted: list = []
    monkeypatch.setattr(
        neon, "branch_id", lambda *a, **k: (_ for _ in ()).throw(neon.BranchNotFound("no such"))
    )
    monkeypatch.setattr(enrol_mod, "mint", lambda *a, **k: minted.append(a))
    argv = ["new@example.org", "scientist", "--limit-usd", "5", "--branch", "alfa"]
    assert main(argv) == 1
    assert "no such" in capsys.readouterr().err
    assert minted == [], "a key was minted for a branch that does not exist"


def _main_with_doubles(monkeypatch, outcome):
    """`main` with both external services replaced, so only its own handling runs."""
    _env(monkeypatch)
    monkeypatch.setattr(neon, "branch_id", lambda *a, **k: "br-alpha")
    monkeypatch.setattr(neon, "connection_url", lambda *a, **k: "postgresql+psycopg://u:p@h/db")
    monkeypatch.setattr(
        enrol_mod.trail_store,
        "engine_from_url",
        lambda url, **k: type("E", (), {"dispose": lambda self: None})(),
    )

    def enrolling(*a, **k):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(enrol_mod, "enrol", enrolling)
    return main(["new@example.org", "scientist", "--limit-usd", "5", "--branch", "alpha"])


@pytest.mark.parametrize(
    "refusal",
    [
        Uncapped("a cap of 0 is not a cap"),
        AlreadyEnrolled("new@example.org is already enrolled"),
        NothingEnrolled("new@example.org was not enrolled"),
    ],
)
def test_an_enrol_level_refusal_comes_back_as_one_sentence_and_a_non_zero_exit(
    monkeypatch, capsys, refusal
):
    """`main`'s docstring promises this for *every* refusal, and until this test
    nothing drove one of `enrol`'s own through the command -- only `main`'s two
    guards. The refusals are the operation's; the command only has to report
    them, and "only has to" is exactly the kind of claim that goes untested."""
    assert _main_with_doubles(monkeypatch, refusal) == 1
    out = capsys.readouterr()
    assert str(refusal) in out.err
    assert out.out == "", "a refusal printed something on the success channel"


def test_a_credential_left_behind_is_named_to_the_operator_by_the_command(monkeypatch, capsys):
    """The one outcome that leaves work for a person. The hash has to survive the
    trip out through `main`, and the key must not -- which is also what makes the
    "no credential is printed" assertion elsewhere falsifiable in both halves
    rather than only in one."""
    left = KeyLeftBehind(f"new@example.org was not enrolled and its credential {HASH} could not")
    assert _main_with_doubles(monkeypatch, left) == 1
    out = capsys.readouterr()
    assert HASH in out.err, "the operator cannot revoke a key they were not told about"
    assert KEY not in out.err


def test_what_the_command_prints_carries_no_credential(monkeypatch, capsys):
    _env(monkeypatch)
    monkeypatch.setattr(neon, "branch_id", lambda *a, **k: "br-alpha")
    monkeypatch.setattr(neon, "connection_url", lambda *a, **k: "postgresql+psycopg://u:p@h/db")
    monkeypatch.setattr(
        enrol_mod.trail_store,
        "engine_from_url",
        lambda url, **k: type("E", (), {"dispose": lambda self: None})(),
    )
    monkeypatch.setattr(
        enrol_mod,
        "enrol",
        lambda *a, **k: Account(email="new@example.org", role=Role.SCIENTIST, openrouter_key=KEY),
    )
    argv = ["new@example.org", "scientist", "--limit-usd", "5", "--branch", "alpha"]
    assert main(argv) == 0
    said = capsys.readouterr().out
    assert "new@example.org" in said and "scientist" in said and "alpha" in said
    assert "$5.00" in said
    # Asserted against the doubles' own values rather than a fixed string, so a
    # changed fixture cannot quietly make this pass.
    assert KEY not in said and HASH not in said
    assert "postgresql" not in said, "the URL carries the password"


# --- withdrawing ---------------------------------------------------------------------


class _WithdrawEngine:
    """Disables, and hands back what the row held. Not a database."""

    def __init__(self, withdrawn=..., error=None):
        self.withdrawn = (
            accounts.Withdrawn("tester@example.org", HASH) if withdrawn is ... else withdrawn
        )
        self.error = error
        self.disabled: list[str] = []

    def disable(self, email):
        if self.error is not None:
            raise self.error
        self.disabled.append(email)
        return self.withdrawn

    def dispose(self):
        pass


@pytest.fixture
def withdrawing(monkeypatch):
    def built(**kwargs):
        engine = _WithdrawEngine(**kwargs)
        monkeypatch.setattr(
            accounts, "disable", lambda engine_, email, **kw: engine_.disable(email)
        )
        monkeypatch.setattr(
            enrol_mod.accounts, "disable", lambda engine_, email, **kw: engine_.disable(email)
        )
        return engine

    return built


def test_withdrawing_disables_the_row_and_revokes_the_credential(withdrawing):
    engine = withdrawing()
    opener = _Opener()
    assert withdraw(engine, "mgmt", "tester@example.org", opener=opener) == "tester@example.org"
    assert engine.disabled == ["tester@example.org"]
    assert opener.methods() == ["DELETE"]
    assert HASH in opener.calls[0][1], "some other credential was revoked"


def test_an_account_that_is_not_there_withdraws_nothing(withdrawing):
    """Nothing is revoked, because nothing names a credential -- and the sentence
    has to send the operator to the table rather than to OpenRouter."""
    opener = _Opener()
    with pytest.raises(NotEnrolled) as refused:
        withdraw(withdrawing(withdrawn=None), "mgmt", "nobody@example.org", opener=opener)
    assert "branch" in str(refused.value), "the commonest cause is not named"
    assert opener.calls == []


def test_a_row_with_no_handle_is_disabled_and_said_to_be_unwithdrawable(withdrawing):
    """Enrolled before the handle was stored. The reader is refused from now on,
    which is half the job, and the operator is told the other half is theirs."""
    engine = withdrawing(withdrawn=accounts.Withdrawn("old@example.org", None))
    opener = _Opener()
    with pytest.raises(CredentialNotWithdrawn) as refused:
        withdraw(engine, "mgmt", "old@example.org", opener=opener)
    assert engine.disabled == ["old@example.org"], "the row was left admitting its reader"
    assert "openrouter.ai" in str(refused.value)
    assert opener.calls == []


def test_a_refused_revoke_leaves_the_account_disabled_and_names_the_key(withdrawing):
    """The order is the decision: the state left behind is a refused account whose
    key a person must revoke, never a live account whose key is gone."""
    engine = withdrawing()
    opener = _Opener(fail={"DELETE": urllib.error.HTTPError("u", 500, "boom", {}, None)})
    with pytest.raises(CredentialNotWithdrawn) as refused:
        withdraw(engine, "mgmt", "tester@example.org", opener=opener)
    assert engine.disabled == ["tester@example.org"]
    assert HASH in str(refused.value), "the operator cannot revoke what is not named"


def test_the_revoke_presents_the_management_key(withdrawing):
    """The double refuses an unauthenticated call, so a mutant dropping the key
    fails here rather than passing on the shape of the request."""
    opener = _Opener()
    withdraw(withdrawing(), "mgmt-secret", "tester@example.org", opener=opener)
    assert opener.authorisations() == ["Bearer mgmt-secret"]


def test_the_command_refuses_without_a_branch(capsys):
    """The same refusal as enrolling, for the same reason read backwards:
    withdrawing from the wrong branch reports success while the account it was
    meant to refuse goes on working."""
    assert withdraw_main(["tester@example.org"]) == 2
    assert "branch" in capsys.readouterr().err


def test_the_command_refuses_an_address_nothing_could_match(capsys):
    assert withdraw_main(["new user@example.org", "--branch", "alpha"]) == 1
    assert "new user@example.org" in capsys.readouterr().err
