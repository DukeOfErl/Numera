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


@pytest.fixture(autouse=True)
def _exercise_the_real_fetch(monkeypatch):
    monkeypatch.setattr(allowance, "fetch", _REAL_FETCH)


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
    assert "monthly" in allowance.as_text(Allowance(remaining=1.0, limit=2.0, resets="monthly"))


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
    def never(request, timeout=None):  # pragma: no cover - must not be called
        raise AssertionError("the provider was asked about a key that does not exist")

    assert allowance.fetch("", opener=never) == Allowance()


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
