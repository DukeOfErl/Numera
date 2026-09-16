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
    """One line for the panel, or "" when there is nothing worth saying.

    Dollars, formatted here rather than through `config.format_usd`, which takes
    the integer micro-dollars this project counts spend in. The provider answers
    in dollars as a float, and converting between the two to print a caption is
    two chances to be out by a million.
    """
    if not allowance.known:
        return ""
    if allowance.limit is None:
        spent = f"{allowance.usage:,.2f}" if allowance.usage is not None else "?"
        return f"Key: ${spent} used, no cap set."
    left = allowance.remaining
    if left is None and allowance.usage is not None:
        left = allowance.limit - allowance.usage
    if left is None:
        return f"Key: ${allowance.limit:,.2f} cap."
    renews = f", renews {allowance.resets}" if allowance.resets else ""
    return f"Key: ${left:,.2f} left of ${allowance.limit:,.2f}{renews}."
