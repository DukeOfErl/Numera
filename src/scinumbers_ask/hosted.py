"""Bring the corpus into a hosted container, once, and refuse a bad copy.

**Deployment branch only.** A hosted container starts with nothing but the git
checkout, and the corpus may not be in it: 21 MB whose licensing is unresolved
(ADR-0170). So it is fetched at boot from somewhere only the deployment can reach --
a release asset on a private repository -- into a path outside the checkout.

Policy rather than agent business, so it sits on the presentation side of the
dependency line with `autobuild`, and it composes with `autobuild` rather than
replacing it: this puts a file where the configured path says, and `corpus_path`
then takes its "a corpus already there is the answer" branch.

**Why the digest is checked and not trusted.** A download truncated at a line
boundary is *valid JSONL* with fewer entries. It would load, index, answer and cite;
the only symptom would be "no entries matched" for questions whose entries were in
the tail, which is indistinguishable from an honest miss. That is the failure this
project exists to prevent, so a copy that does not match is refused rather than
served. For the same reason an absent digest is a refusal too: a deployment that
forgot to configure one must not silently get an unverified corpus.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path

from .corpus import CorpusUnavailable

#: Long enough for 21 MB over a slow link, short enough that a hung fetch fails the
#: page rather than holding every visitor behind the cache lock indefinitely.
TIMEOUT_SECONDS = 300

_CHUNK = 1024 * 1024


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Carry the token to the API, never to wherever it redirects.

    A private release asset answers with a 302 to a signed storage URL, and that URL
    rejects a request still carrying an `Authorization` header -- with a 400 that
    reads like a permissions problem, which is the wrong place to go looking.
    urllib's default handler copies every header onto the redirected request, so it
    has to be taken off here. `curl -L` does this by itself, which is why a curl
    check of the same URL succeeds where the naive Python version fails.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fresh = super().redirect_request(req, fp, code, msg, headers, newurl)
        if fresh is not None:
            fresh.remove_header("Authorization")
        return fresh


def _digest_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_corpus(url: str, token: str, dest: Path, expected_sha256: str) -> Path:
    """Put the corpus at `dest`, or explain why there is none.

    Returns `dest` untouched when a corpus is already there: the container's disk is
    ephemeral, so this runs once per cold start, and re-downloading a file that is
    already present would only add a minute to every restart.

    Raises `CorpusUnavailable` for everything a person can fix -- no URL, no digest,
    a fetch that failed, a copy that does not match -- because both drivers already
    render that as a sentence instead of a stack trace.
    """
    if dest.is_file():
        return dest
    if not url:
        raise CorpusUnavailable(
            "No CORPUS_URL is configured, so there is nothing to fetch and no corpus "
            "in this container. Set it to the release asset's API URL."
        )
    if not expected_sha256.strip():
        # Refused rather than skipped. A missing digest is a configuration slip, and
        # the failure it would let through -- a truncated corpus that parses -- is
        # exactly the one this check exists for, so the absence must not be the
        # quiet path.
        raise CorpusUnavailable(
            "No CORPUS_SHA256 is configured. The corpus is not served unverified: a "
            "truncated download is valid JSONL and answers plausibly from whatever "
            "arrived."
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    headers = {"Accept": "application/octet-stream", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        opener = urllib.request.build_opener(_DropAuthOnRedirect)
        with opener.open(urllib.request.Request(url, headers=headers), timeout=TIMEOUT_SECONDS) as (
            response
        ):
            with partial.open("wb") as out:
                shutil.copyfileobj(response, out)
    except OSError as exc:
        # URLError, HTTPError and a full disk are all OSError. Whatever went wrong,
        # the outcome for the reader is that there is no corpus. The URL is named
        # and the token is not: a message on a public page must not carry it.
        partial.unlink(missing_ok=True)
        raise CorpusUnavailable(
            f"Could not fetch the corpus from {url}: {exc}. If the token has expired, "
            "a private asset answers 404 rather than 401."
        ) from exc

    digest = _digest_of(partial)
    if digest != expected_sha256.strip().lower():
        partial.unlink(missing_ok=True)
        raise CorpusUnavailable(
            f"The corpus fetched from {url} has digest {digest[:12]}, not the expected "
            f"{expected_sha256.strip().lower()[:12]}. Refusing to answer from it: a "
            "truncated or replaced corpus parses perfectly and answers from whatever "
            "it holds."
        )
    # Renamed into place only once it is known to be whole, so nothing -- a reader,
    # a restart, a second container -- can ever read a half-written corpus. The same
    # discipline `bionumbers_ingest.io` uses for the file it writes.
    partial.replace(dest)
    return dest
