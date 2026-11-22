"""What is left on one tester's provider key, for the page to show them.

**Presentation, and the placement is the point.** This asks the model provider
how much credit a key has left; the agent must not be able to reach it. An agent
that could read its own funding could act on it -- shorten an answer because the
budget is low, or report a figure it was never given to reason about -- and the
spend the agent *is* allowed to know is already an event it emits.
`tests/test_driver_independence.py` holds the line.

**The figure is the provider's, not ours.** The run ledger counts what this
deployment has spent; this counts what OpenRouter will still honour, which is the
number a tester actually wants when they are told their allowance is spent. The
two can disagree -- a key used elsewhere, a cap changed mid-month -- and where
they do, this one is right.

Verified against openrouter.ai's own documentation on 2026-09-16: `GET
/api/v1/key` reports the calling key's credit limits, and `limit_remaining` is
the field their "limits" page names as where to check a per-key cap. The response
is read defensively all the same: a shape that changed is a caption that
disappears, never a page that breaks.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

KEY_ENDPOINT = "https://openrouter.ai/api/v1/key"

#: Seconds to wait. Short, because this runs while a reader is looking at a page
#: that is already drawn: a slow answer here is a page that hangs for a figure
#: nobody asked to wait for.
TIMEOUT_S = 4


@dataclass(frozen=True)
class Allowance:
    """What the provider says is left on a key.

    Every field optional because every one of them can be absent: a key with no
    cap reports no limit, and a response whose shape moved reports nothing we
    recognise. `None` means "not known", never "zero" -- the difference matters,
    because zero is the state that stops a tester working.
    """

    remaining: float | None = None
    limit: float | None = None
    usage: float | None = None
    resets: str | None = None

    @property
    def known(self) -> bool:
        """Whether there is anything worth putting on the page.

        Usage counts, even with no cap beside it: a key issued without a limit is
        a configuration the operator meant to make and may not have, and "no cap
        set" is the line that tells them.
        """
        return any(value is not None for value in (self.remaining, self.limit, self.usage))


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse(payload: Any) -> Allowance:
    """The allowance in a provider response, or an empty one.

    Split from the fetch so the shape can be tested without a network, which is
    the half that actually changes.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}
    resets = data.get("limit_reset")
    return Allowance(
        remaining=_number(data.get("limit_remaining")),
        limit=_number(data.get("limit")),
        usage=_number(data.get("usage")),
        resets=resets if isinstance(resets, str) else None,
    )


@dataclass(frozen=True)
class Probe:
    """What the provider said when asked about a key.

    `rejected` is the narrow, load-bearing part: **the provider said this key is
    not usable**, which is a 401 or a 403 and nothing else. Every other failure --
    a timeout, DNS, a 500, a body we cannot read -- leaves it `False`, because
    the two must not be confused. Refusing a reader on a rejected key is telling
    them the truth; refusing one because OpenRouter blinked would lock out every
    tester whenever the provider has a bad minute, to guard against a case the
    question's own ending already handles.
    """

    allowance: Allowance = Allowance()
    rejected: bool = False


#: The statuses that mean the credential itself is the problem. A 402 is *not*
#: here: a key with no credit left is a valid key, and a spent allowance is an
#: ending with a sentence of its own (ADR-0600).
REJECTING_STATUSES = (401, 403)


def probe(api_key: str, *, opener=urllib.request.urlopen) -> Probe:
    """Ask the provider about a key: what is left on it, and whether it works.

    One cheap call, made once per account per session at sign-in. Without it an
    unusable credential is discovered only when a reader asks something: the model
    call fails, the tools retrieve nothing, and the answer that comes back says
    it found nothing in the corpus -- which reads as a gap in the data rather than
    a broken key, and is the one failure this project most wants not to look
    ordinary.
    """
    if not api_key:
        return Probe()
    request = urllib.request.Request(
        KEY_ENDPOINT, headers={"Authorization": f"Bearer {api_key}"}, method="GET"
    )
    try:
        with opener(request, timeout=TIMEOUT_S) as response:
            return Probe(parse(json.loads(response.read().decode("utf-8"))))
    except urllib.error.HTTPError as refused:
        return Probe(rejected=refused.code in REJECTING_STATUSES)
    except Exception:  # noqa: BLE001 - see `fetch`
        return Probe()


def fetch(api_key: str, *, opener=urllib.request.urlopen) -> Allowance:
    """Ask the provider what is left on this key. Never raises.

    An unreachable provider, a refused key, a timeout and a response we cannot
    read all produce the same empty answer, because the page's response to all
    four is the same: say nothing rather than guess. The key travels in the
    header and is never logged -- `complain` would put it on the operator's
    stderr, and a credential in a log is a credential.
    """
    if not api_key:
        return Allowance()
    request = urllib.request.Request(
        KEY_ENDPOINT, headers={"Authorization": f"Bearer {api_key}"}, method="GET"
    )
    try:
        with opener(request, timeout=TIMEOUT_S) as response:
            return parse(json.loads(response.read().decode("utf-8")))
    except Exception:  # noqa: BLE001 - see below
        # Every exception, not a list of the ones worth naming. This exists to
        # put a caption on a page that is already drawn, so there is no failure
        # here whose right answer is anything but "say nothing": a refused key, a
        # DNS failure, a proxy that rejects the host, a body that is not JSON, a
        # library raising something its own documentation does not mention. A
        # narrower catch let a blocked outbound connection take down the whole
        # page in testing, which is precisely the trade this module must not make.
        # `BaseException` stays uncaught: a person pressing Ctrl-C is not a
        # provider outage, the same line `trail_store` draws.
        return Allowance()


def as_text(allowance: Allowance) -> str:
    """The key's own standing, as a fragment for the spend line, or "" when there
    is nothing worth saying.

    A fragment rather than a sentence: it is read inside the parenthesis of
    "$0.12 of $2.00 ($4.89 on key of weekly $5.00)", where the run budget is the
    subject and this is the ceiling behind it. Two captions said the same kind of
    thing in two registers and made the reader work out which bound them first.

    Dollars, formatted here rather than through `config.format_usd`, which takes
    the integer micro-dollars this project counts spend in. The provider answers
    in dollars as a float, and converting between the two to print a caption is
    two chances to be out by a million.

    Where the provider states a `remaining`, that figure is what goes on the page,
    even when it disagrees with `limit - usage` -- a cap changed mid-period, or a
    key spent elsewhere, and the provider's own figure is the one a tester acts
    on. The subtraction is only for a response that states no remaining at all.

    A `limit_remaining` arriving with no `limit` beside it is deliberately not
    shown: with no cap there is nothing for a remaining figure to be remaining
    of, so the uncapped line reports the usage the provider gave and says there is
    no cap. An omission, decided, rather than a figure derived from something
    else.
    """
    if not allowance.known:
        return ""
    if allowance.limit is None:
        spent = f"{allowance.usage:,.2f}" if allowance.usage is not None else "?"
        return f"${spent} used on key, no cap"
    left = allowance.remaining
    if left is None and allowance.usage is not None:
        left = allowance.limit - allowance.usage
    if left is None:
        return f"${allowance.limit:,.2f} cap on key"
    every = f"{allowance.resets} " if allowance.resets else ""
    return f"${left:,.2f} on key of {every}${allowance.limit:,.2f}"
