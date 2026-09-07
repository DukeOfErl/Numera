"""The hosted fetch: what it refuses, and what it leaves on disk when it does.

Deployment-branch tests. They matter more than their size suggests, because every
failure here is silent from the answer side: a corpus that is short, stale or
half-written still parses, still indexes, and still answers -- with "no entries
matched" for whatever it is missing, which looks exactly like an honest miss.

`file://` URLs throughout, so nothing reaches a network or needs a token. What that
cannot cover is the redirect handling, which only a real private asset exercises;
the check for that is the `curl -L` in the deployment notes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scinumbers_ask.corpus import CorpusUnavailable
from scinumbers_ask.hosted import fetch_corpus

CONTENT = b'{"entry_id": 100002, "property": "Cell diameter"}\n'
DIGEST = hashlib.sha256(CONTENT).hexdigest()


@pytest.fixture
def source(tmp_path: Path) -> str:
    served = tmp_path / "served.jsonl"
    served.write_bytes(CONTENT)
    return served.as_uri()


def test_a_matching_corpus_lands_at_the_configured_path(source, tmp_path):
    dest = tmp_path / "corpus" / "bionumbers.jsonl"
    assert fetch_corpus(source, "", dest, DIGEST) == dest
    assert dest.read_bytes() == CONTENT


def test_a_corpus_already_there_is_not_fetched_again(tmp_path):
    """The disk is ephemeral, so this runs once per cold start -- but a restart that
    re-downloaded a file already present would add a minute to every one."""
    dest = tmp_path / "bionumbers.jsonl"
    dest.write_bytes(b"whatever is already here\n")
    # A URL that could not possibly be fetched: reaching it at all is the failure.
    assert fetch_corpus("file:///nonexistent", "", dest, DIGEST) == dest
    assert dest.read_bytes() == b"whatever is already here\n"


def test_a_corpus_that_does_not_match_is_refused_and_left_nowhere(source, tmp_path):
    """The failure this whole module exists for. A download cut at a line boundary is
    valid JSONL: it loads, indexes and answers, and the only symptom is that entries
    in the missing tail are reported as not found."""
    dest = tmp_path / "bionumbers.jsonl"
    with pytest.raises(CorpusUnavailable, match="Refusing to answer from it"):
        fetch_corpus(source, "", dest, "0" * 64)
    assert not dest.exists(), "a rejected corpus must not be left where the app would load it"
    assert not list(dest.parent.glob("*.partial")), "nor its scratch file"


def test_no_digest_configured_is_a_refusal_not_a_skip(source, tmp_path):
    """A deployment that forgot to set one must not quietly get an unverified corpus:
    the absence of the check cannot be the quiet path when the check is the only
    thing standing between a truncated file and a plausible answer."""
    dest = tmp_path / "bionumbers.jsonl"
    with pytest.raises(CorpusUnavailable, match="CORPUS_SHA256"):
        fetch_corpus(source, "", dest, "   ")
    assert not dest.exists()


def test_a_digest_pasted_with_spaces_or_capitals_still_matches(source, tmp_path):
    """It arrives by copy and paste out of `sha256sum` into a secrets box."""
    dest = tmp_path / "bionumbers.jsonl"
    assert fetch_corpus(source, "", dest, f"  {DIGEST.upper()}  ") == dest


def test_a_fetch_that_fails_says_so_rather_than_raising_a_url_error(tmp_path):
    """Both drivers render `CorpusUnavailable` as a sentence; a URLError would reach
    the terminal as a traceback and the page as Streamlit's exception panel."""
    dest = tmp_path / "bionumbers.jsonl"
    missing = (tmp_path / "not-there.jsonl").as_uri()
    with pytest.raises(CorpusUnavailable, match="Could not fetch the corpus"):
        fetch_corpus(missing, "", dest, DIGEST)
    assert not dest.exists()


def test_no_url_configured_names_what_is_missing(tmp_path):
    with pytest.raises(CorpusUnavailable, match="CORPUS_URL"):
        fetch_corpus("", "", tmp_path / "bionumbers.jsonl", DIGEST)


def test_the_token_never_reaches_the_message(tmp_path):
    """These sentences are drawn on a public page."""
    dest = tmp_path / "bionumbers.jsonl"
    missing = (tmp_path / "not-there.jsonl").as_uri()
    with pytest.raises(CorpusUnavailable) as raised:
        fetch_corpus(missing, "github_pat_SECRETVALUE", dest, DIGEST)
    assert "SECRETVALUE" not in str(raised.value)


# -- through the page -----------------------------------------------------


APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


@pytest.fixture
def fresh_caches():
    """`_corpus_in_this_container` takes no arguments, so one fetch serves the life
    of the process -- which is the point in a container and a leak between tests."""
    import streamlit as st

    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def test_the_page_shows_a_refused_corpus_as_a_sentence(fresh_caches, monkeypatch, tmp_path):
    """A reader meeting this sees a message, not Streamlit's exception panel with a
    stack they did not cause -- the same treatment every other corpus failure gets."""
    from streamlit.testing.v1 import AppTest

    served = tmp_path / "served.jsonl"
    served.write_bytes(CONTENT)
    monkeypatch.setenv("CORPUS_URL", served.as_uri())
    monkeypatch.setenv("CORPUS_SHA256", "0" * 64)
    monkeypatch.setenv("SCINUMBERS_CORPUS", str(tmp_path / "corpus.jsonl"))
    monkeypatch.setenv("SCINUMBERS_CHECKPOINTS", str(tmp_path / "c.sqlite"))

    at = AppTest.from_file(APP, default_timeout=30).run()

    assert not at.exception, "a bad corpus is a condition to report, not a traceback"
    assert any("Refusing to answer from it" in error.value for error in at.error)
    assert not at.chat_input, "and no question is taken against a corpus we would not trust"


def test_no_corpus_url_leaves_the_page_behaving_as_it_does_on_main(fresh_caches, monkeypatch, repo):
    """Without a URL this is not a hosted run, and the fetch must not fire: it is
    what lets this branch be run on a laptop, and what keeps the driver tests
    driving the same script everyone else does."""
    from streamlit.testing.v1 import AppTest

    from scinumbers_ask import web

    monkeypatch.delenv("CORPUS_URL", raising=False)
    monkeypatch.delenv("CORPUS_SHA256", raising=False)
    monkeypatch.setattr(web, "resources", lambda corpus=None: (repo, _NoAgent()))

    at = AppTest.from_file(APP, default_timeout=30).run()

    assert not at.exception
    assert not at.error
    assert at.chat_input


def test_a_secret_pasted_without_quotes_still_configures_the_run(fresh_caches, monkeypatch, repo):
    """Every setting here is a string in TOML, and a number pasted without its quotes
    arrives as a float. Skipped, it left the variable unset and the run on its own
    default -- a per-question ceiling three times the configured one, from a missing
    pair of quotes, with nothing on the page to say so."""
    import os

    from streamlit.testing.v1 import AppTest

    from scinumbers_ask import web

    monkeypatch.delenv("CORPUS_URL", raising=False)
    monkeypatch.delenv("SCINUMBERS_QUESTION_CEILING_USD", raising=False)
    monkeypatch.setattr(web, "resources", lambda corpus=None: (repo, _NoAgent()))

    at = AppTest.from_file(APP, default_timeout=30)
    at.secrets["SCINUMBERS_QUESTION_CEILING_USD"] = 0.20  # a TOML float, not a string
    at.run()

    assert not at.exception
    assert os.environ["SCINUMBERS_QUESTION_CEILING_USD"] == "0.2"


class _NoAgent:
    """Enough agent for the page to draw: it is never asked anything here."""

    run_budget = 1_200_000

    def run_spend(self) -> int:
        return 0
