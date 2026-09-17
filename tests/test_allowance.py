"""What the provider says is left on a key, and the page's silence when it will not say.

The parsing is separated from the fetch because the parsing is the half that
changes: OpenRouter's response shape is theirs to move, and a shape we no longer
recognise has to become a missing caption rather than a broken page or -- worse --
a confident wrong number, since this is the figure a tester acts on when told
their allowance is spent.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from scinumbers_ask import allowance
from scinumbers_ask.allowance import Allowance

#: Captured before `conftest` stubs the module attribute for the whole suite.
#: That stub keeps every other test off the network; this file is where the real
#: fetch is exercised, against a stub opener rather than against OpenRouter.
_REAL_FETCH = allowance.fetch


_REAL_PROBE = allowance.probe


@pytest.fixture(autouse=True)
def _exercise_the_real_calls(monkeypatch):
    monkeypatch.setattr(allowance, "fetch", _REAL_FETCH)
    monkeypatch.setattr(allowance, "probe", _REAL_PROBE)


class _Response:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(payload):
    def open_it(request, timeout=None):
        open_it.request = request
        open_it.timeout = timeout
        return _Response(payload)

    return open_it


# --- the shape the provider documents ------------------------------------------------


def test_a_capped_key_reports_what_is_left():
    """`GET /api/v1/key` wraps its answer in `data`; verified against openrouter.ai's
    own limits page on 2026-09-16, which names `limit_remaining` as where to check."""
    left = allowance.parse(
        {"data": {"label": "tester", "usage": 1.6, "limit": 5.0, "limit_remaining": 3.4}}
    )
    assert (left.remaining, left.limit, left.usage) == (3.4, 5.0, 1.6)
    assert "3.40" in allowance.as_text(left) and "5.00" in allowance.as_text(left)


def test_an_unwrapped_body_is_read_too():
    """Defensive rather than speculative: the wrapper is one of the two shapes an
    API of this kind returns, and guessing wrong costs a caption."""
    assert allowance.parse({"limit_remaining": 2.0, "limit": 4.0}).remaining == 2.0


def test_a_key_with_no_cap_says_so_rather_than_inventing_one():
    line = allowance.as_text(allowance.parse({"data": {"usage": 2.5, "limit": None}}))
    assert "no cap" in line and "2.50" in line


def test_what_is_left_is_worked_out_when_only_usage_and_a_cap_are_given():
    line = allowance.as_text(Allowance(limit=5.0, usage=1.0))
    assert "4.00" in line and "5.00" in line


def test_the_renewal_is_named_when_the_provider_names_it():
    """The renewal is named when there is one; that no clause appears when there
    is not is deliberately *not* asserted here.

    Mutation testing offers both -- appending ", renews None" to every line, and
    swapping the empty alternative for a sentinel, both survive the suite. Left
    alive on purpose: this is the panel's wording, which no requirement fixes and
    which a reader would see and report the moment it were wrong. Pinning the
    absent clause would make the caption's punctuation a contract.
    """
    assert "monthly" in allowance.as_text(Allowance(remaining=1.0, limit=2.0, resets="monthly"))


def test_the_renewal_comes_off_the_payload_and_is_stated_as_the_provider_gave_it():
    """`user-identity`: what the interface states about a credential is the provider's
    own figures, or nothing.

    The test above it builds the `Allowance` by hand, so nothing read `limit_reset`
    off a payload: blanking it, renaming the key, or dropping the guard around it
    all left the suite green.
    """
    left = allowance.parse(
        {"data": {"usage": 1.6, "limit": 5.0, "limit_remaining": 2.9, "limit_reset": "monthly"}}
    )
    assert left.resets == "monthly"
    assert "renews monthly" in allowance.as_text(left)


@pytest.mark.parametrize(
    "reset",
    [None, 1735689600, 0, {"every": "month"}, ["monthly"]],
    ids=["absent", "a timestamp", "a zero", "an object", "a list"],
)
def test_a_renewal_the_provider_does_not_put_in_words_is_not_stated_at_all(reset):
    """The negative varies the dimension the guard reads -- what *kind* of thing
    `limit_reset` holds -- on a payload that is otherwise complete, rather than
    varying only the outcome. A renewal printed from a unix timestamp would be a
    sentence telling a tester their key renews in 1735689600."""
    left = allowance.parse({"data": {"limit": 5.0, "limit_remaining": 2.9, "limit_reset": reset}})
    assert left.resets is None
    assert "renews" not in allowance.as_text(left)


def test_the_providers_own_remaining_is_what_is_shown_where_it_disagrees_with_the_cap():
    """A `limit_remaining` that is not `limit - usage` is the real case, not a
    contrived one: a cap changed mid-period, or a key spent from somewhere else.
    The provider's figure is the one a tester acts on, so it is the one shown.

    The fixture the other tests use has 5.0 - 1.6 = 3.4 and a `limit_remaining` of
    3.4, so it could not tell the two apart at all.
    """
    line = allowance.as_text(
        allowance.parse({"data": {"usage": 1.6, "limit": 5.0, "limit_remaining": 2.9}})
    )
    assert "$2.90 left" in line
    assert "3.40" not in line, "the worked-out figure, which the provider's own contradicts"


def test_with_no_remaining_from_the_provider_there_is_none_of_theirs_to_prefer():
    """The negative for the one above, varying the single field the preference
    reads on an otherwise identical payload."""
    line = allowance.as_text(allowance.parse({"data": {"usage": 1.6, "limit": 5.0}}))
    assert "$3.40 left" in line
    assert "2.90" not in line


# --- nothing known is nothing shown -----------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [{}, {"data": {}}, {"data": None}, [], "not json at all", {"data": {"limit_remaining": None}}],
    ids=["empty", "no fields", "null data", "a list", "a string", "an explicit null"],
)
def test_a_response_we_cannot_read_says_nothing(payload):
    """Silence, not a guess: a wrong figure here is one a tester would act on."""
    assert allowance.as_text(allowance.parse(payload)) == ""


def test_a_nonsense_number_is_not_a_number():
    assert allowance.parse({"data": {"limit_remaining": "lots", "limit": True}}).known is False


# --- the network never breaks the page ----------------------------------------------------


@pytest.mark.parametrize(
    "boom",
    [
        urllib.error.URLError("no route"),
        TimeoutError("too slow"),
        OSError("refused"),
        ValueError("not json"),
    ],
    ids=["unreachable", "timeout", "refused", "unparseable"],
)
def test_no_failure_escapes_the_fetch(boom):
    def explode(request, timeout=None):
        raise boom

    assert allowance.fetch("sk-or-v1-x", opener=explode) == Allowance()


def test_an_empty_key_is_not_asked_about():
    """The opener records the call instead of raising, and the claim is asserted
    after `fetch` has returned.

    `fetch` catches every exception, including an `AssertionError` raised inside
    the opener, so the earlier shape could not fail: it passed whether or not the
    provider was asked. Mutation testing cannot find that -- inverting
    `if not api_key` breaks the positive cases as well, so the mutant dies for
    the wrong reason and the blind test is never implicated.
    """
    asked = []

    def record(request, timeout=None):
        asked.append(request)
        return _Response({"data": {"limit_remaining": 9.0, "limit": 9.0}})

    assert allowance.fetch("", opener=record) == Allowance()
    assert asked == [], "the provider was asked about a key that does not exist"


def test_what_the_provider_answered_is_what_the_fetch_returns():
    """`fetch` could have returned an empty `Allowance` on every successful
    response and the suite would have stayed green: the two tests that called it
    with a real payload asserted only the outgoing request. `probe` asserts its
    own result, which is the shape this was missing.

    Every field holds a different number, so a field read off the wrong key shows
    rather than coinciding.
    """
    opener = _opener(
        {"data": {"usage": 1.6, "limit": 5.0, "limit_remaining": 2.9, "limit_reset": "monthly"}}
    )
    assert allowance.fetch("sk-or-v1-x", opener=opener) == Allowance(
        remaining=2.9, limit=5.0, usage=1.6, resets="monthly"
    )


def test_the_key_travels_in_the_header_and_the_request_is_bounded():
    opener = _opener({"data": {"limit_remaining": 1.0, "limit": 2.0}})
    allowance.fetch("sk-or-v1-secret", opener=opener)
    assert opener.request.get_header("Authorization") == "Bearer sk-or-v1-secret"
    assert opener.request.full_url == allowance.KEY_ENDPOINT
    assert opener.timeout == allowance.TIMEOUT_S, "an unbounded call hangs the page"


def test_the_credential_is_not_in_the_url_where_a_log_would_keep_it():
    opener = _opener({"data": {"limit_remaining": 1.0}})
    allowance.fetch("sk-or-v1-secret", opener=opener)
    assert "sk-or-v1-secret" not in opener.request.full_url


# --- whether the key works at all ------------------------------------------------------


def _refusing(status):
    def open_it(request, timeout=None):
        raise urllib.error.HTTPError(allowance.KEY_ENDPOINT, status, "no", {}, None)

    return open_it


@pytest.mark.parametrize("status", [401, 403], ids=["unauthorized", "forbidden"])
def test_a_key_the_provider_refuses_is_reported_as_rejected(status):
    assert allowance.probe("sk-or-v1-bad", opener=_refusing(status)).rejected is True


@pytest.mark.parametrize(
    "status", [402, 429, 500, 502, 503], ids=["no credit", "rate limited", "500", "502", "503"]
)
def test_every_other_status_leaves_the_key_believed_good(status):
    """The distinction the door depends on. A 402 especially: a key with no credit
    left is a *valid* key, and a spent allowance is an ending with its own
    sentence -- refusing sign-in for it would replace a precise message with a
    wrong one."""
    assert allowance.probe("sk-or-v1-spent", opener=_refusing(status)).rejected is False


@pytest.mark.parametrize(
    "boom",
    [urllib.error.URLError("no route"), TimeoutError("slow"), OSError("refused")],
    ids=["unreachable", "timeout", "refused"],
)
def test_a_provider_we_cannot_reach_does_not_condemn_the_key(boom):
    """Locking every tester out because OpenRouter had a bad minute is the worse
    failure, and the question's own ending still covers a key that truly fails."""

    def explode(request, timeout=None):
        raise boom

    probe = allowance.probe("sk-or-v1-fine", opener=explode)
    assert probe.rejected is False
    assert probe.allowance == Allowance()


def test_a_working_key_comes_back_with_its_allowance_and_no_rejection():
    probe = allowance.probe("sk-or-v1-ok", opener=_opener({"data": {"limit_remaining": 2.0}}))
    assert probe.rejected is False
    assert probe.allowance.remaining == 2.0


def test_an_empty_key_is_not_probed():
    """Recorded rather than raised, for the reason given on the fetch's own
    empty-key test: `probe` swallows every exception the opener can raise, so an
    `AssertionError` from inside it proves nothing."""
    asked = []

    def record(request, timeout=None):
        asked.append(request)
        return _Response({"data": {"limit_remaining": 9.0}})

    assert allowance.probe("", opener=record) == allowance.Probe()
    assert asked == [], "the provider was asked about a key that does not exist"


def test_the_probe_asks_about_this_account_s_own_key_and_is_bounded():
    """`user-identity`: an enrolled account that signs in proceeds with its role.

    The request is the input to the one classification the door depends on, and
    nothing held it: blanking the request, dropping the `Authorization` header or
    removing the key from it all passed the whole suite, because every probe test
    asserts what came *back* and none asserts what went *out*. The fetch beside it
    has had this assertion since it was written; the probe never did.

    What that costs is the whole deployment rather than one caption. A probe with
    no credential in it is refused 401 by the provider, `rejected` is True for
    every account, and every enrolled tester meets the credential-rejected door
    instead of the page -- the exact failure the module's own docstring says must
    not happen because OpenRouter had a bad minute, arrived at by our own request
    instead.

    The endpoint and the bound are here for the same reason they are on the fetch:
    `user-identity` requires that no credential appears on any page a reader sees,
    and a key in a URL is a key in every log and every error line; an unbounded
    call hangs the sign-in door, which is a page that never proceeds.
    """
    opener = _opener({"data": {"limit_remaining": 1.0, "limit": 2.0}})
    allowance.probe("sk-or-v1-secret", opener=opener)

    assert opener.request.get_header("Authorization") == "Bearer sk-or-v1-secret"
    assert opener.request.full_url == allowance.KEY_ENDPOINT
    assert "sk-or-v1-secret" not in opener.request.full_url
    assert opener.request.get_method() == "GET", "asking about a key is a read"
    assert opener.timeout == allowance.TIMEOUT_S, "an unbounded call hangs the door"


def test_two_accounts_are_asked_about_separately():
    """The dimension the request actually reads is *which* key it was handed.

    A probe that carried a constant -- the environment's key, the first key it
    ever saw -- would satisfy the test above completely, and would report one
    account's standing as another's. So this varies the credential and nothing
    else, which the test above cannot do with one key in it.
    """
    first, second = _opener({"data": {}}), _opener({"data": {}})
    allowance.probe("sk-or-v1-alice", opener=first)
    allowance.probe("sk-or-v1-bob", opener=second)

    assert first.request.get_header("Authorization") == "Bearer sk-or-v1-alice"
    assert second.request.get_header("Authorization") == "Bearer sk-or-v1-bob"
