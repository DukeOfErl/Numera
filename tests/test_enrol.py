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

import pytest

from scinumbers_ask import accounts, neon
from scinumbers_ask import enrol as enrol_mod
from scinumbers_ask.accounts import Account, AlreadyEnrolled
from scinumbers_ask.enrol import (
    KeyLeftBehind,
    MintFailed,
    NothingEnrolled,
    Uncapped,
    enrol,
    main,
    mint,
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
    """Answers by (method, url-fragment), and records what it was asked."""

    def __init__(self, routes=None, fail=None):
        self.routes = routes or {}
        self.fail = fail or {}
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[dict] = []

    def __call__(self, request, timeout=None):
        # `get_method()`, not `.method`: urllib only sets the attribute when the
        # caller passed one, so a GET built without it has no such attribute.
        method, url = request.get_method(), request.full_url
        self.calls.append((method, url))
        if request.data:
            self.bodies.append(json.loads(request.data.decode("utf-8")))
        for fragment, error in self.fail.items():
            if fragment in f"{method} {url}":
                raise error
        for fragment, payload in self.routes.items():
            if fragment in f"{method} {url}":
                return _Response(payload)
        return _Response({})

    def methods(self):
        return [method for method, _ in self.calls]


def _minted(limit=5.0, reset="monthly"):
    return {"key": KEY, "data": {"hash": HASH, "limit": limit, "limit_reset": reset}}


class _Engine:
    """Inserts, or fails where told. Not a database: `test_accounts.py` covers that."""

    def __init__(self, error=None):
        self.error = error
        self.inserted: list[tuple] = []

    def insert(self, email, role, key):
        if self.error is not None:
            raise self.error
        self.inserted.append((email, role, key))
        return Account(email=email, role=role, openrouter_key=key)


@pytest.fixture
def engine(monkeypatch):
    built = _Engine()

    def insert(engine_, email, role, key, **kwargs):
        return engine_.insert(email, role, key)

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


# --- the happy path ----------------------------------------------------------------


def test_enrolling_mints_a_capped_key_and_records_the_account(engine):
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": _minted()})
    account = enrol(engine, "mgmt", "new@example.org", Role.SCIENTIST, 5, opener=opener)
    assert account.openrouter_key == KEY
    assert engine.inserted == [("new@example.org", Role.SCIENTIST, KEY)]
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


def test_a_reset_the_patch_cannot_fix_is_revoked_and_refused():
    opener = _Opener(
        {
            "POST https://openrouter.ai/api/v1/keys": _minted(reset=None),
            "PATCH": {"data": {"hash": HASH, "limit": 5.0, "limit_reset": None}},
        }
    )
    with pytest.raises(MintFailed):
        mint("mgmt", name="new@example.org", limit_usd=5, opener=opener)
    assert opener.methods() == ["POST", "PATCH", "DELETE"]


def test_a_response_with_no_key_is_refused():
    opener = _Opener({"POST https://openrouter.ai/api/v1/keys": {"data": {"hash": HASH}}})
    with pytest.raises(MintFailed):
        mint("mgmt", name="new@example.org", limit_usd=5, opener=opener)
    assert "DELETE" not in opener.methods(), "there is no usable key to withdraw"


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
    monkeypatch.setattr(neon, "branch_id", lambda *a, **k: called.append(a))
    monkeypatch.setattr(enrol_mod, "enrol", lambda *a, **k: called.append(a))
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
