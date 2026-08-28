"""Every marker the table draws can actually fire, measured on a real corpus.

A marker whose condition never holds is worse than no marker: it passes every
test, draws nothing, and quietly promises a distinction the table never makes.
Its count is then a claim about the world -- "no entry in this corpus lacks a
measurement method" -- and a zero needs an argument from the code before anyone
believes it.

The case that prompted this came from the ingestion side. A flag reporting
stripped markup read zero across the whole corpus while 71 per cent of records
were contaminated: its condition was evaluated on the text *before* the unescape
that turned `&lt;IMG` into live markup, so it could never hold. Nothing was red.
The corpus simply said the problem did not occur.

Neither instrument already in use would have caught it. Coverage says the line
ran, and it did -- it evaluated, and returned false, every time. Fault seeding
perturbs code a test already reaches, and no test reached a true branch here.
Only counting the condition against real data answers it.

Marked `corpus` and skipped by default, because the corpus is an external input
kept out of the repository (ADR-0170) and the default suite runs on a six-entry
fixture -- a fixture written to match the same assumptions the markers encode,
which is precisely why it cannot test them.

    BIONUMBERS_ASK_CORPUS=/path/to/corpus.jsonl uv run pytest -m corpus
"""

from __future__ import annotations

import os
from collections.abc import Callable

import pytest

from bionumbers_ask.corpus import Entry, load
from bionumbers_ask.entries_table import NO_METHOD, NO_SCALAR
from bionumbers_ask.units import dimension

pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(
        not os.environ.get("BIONUMBERS_ASK_CORPUS"),
        reason="set BIONUMBERS_ASK_CORPUS to check the markers against a real corpus",
    ),
]

# Each marker beside the condition that raises it. Paired here so a reader can
# see what a mark on a row actually asserts, and so adding a marker without a
# line here is a visible omission rather than a silent one.
MARKERS: dict[str, Callable[[Entry], bool]] = {
    f"{NO_METHOD} no measurement method recorded": (
        lambda e: not e.measurement_method.strip()
    ),
    f"{NO_SCALAR} no scalar value recorded": (
        lambda e: e.value is None and e.range_low is None and e.range_high is None
    ),
    "a unit the dimension table does not classify": lambda e: dimension(e.units) is None,
}

# Not here, and deliberately. The cited-but-not-retrieved mark is a property of an
# answer against what a question retrieved, not of an entry, so no corpus can say
# whether it fires. `tests/test_web_driver.py` and the terminal suite cover it
# against constructed answers, which is the only place it can be covered.


@pytest.fixture(scope="module")
def entries() -> tuple[Entry, ...]:
    return load(os.environ["BIONUMBERS_ASK_CORPUS"])


@pytest.mark.parametrize("description", list(MARKERS))
def test_the_marker_can_fire(description, entries):
    holds = sum(1 for entry in entries if MARKERS[description](entry))
    assert holds, (
        f"no entry of {len(entries)} satisfies '{description}', so the mark can "
        "never be drawn -- either its condition is wrong or the corpus has changed"
    )


@pytest.mark.parametrize("description", list(MARKERS))
def test_the_marker_is_not_drawn_on_everything(description, entries):
    """A mark on every row distinguishes nothing, and a reader learns to skip it."""
    holds = sum(1 for entry in entries if MARKERS[description](entry))
    assert holds < len(entries), f"'{description}' holds for every entry"


def test_more_than_one_dimension_is_represented(entries):
    """Otherwise the footnote warning that cited entries measure different kinds
    of quantity could never appear, whatever an answer cited."""
    kinds = {dimension(entry.units) for entry in entries}
    kinds.discard(None)
    assert len(kinds) > 1, f"only {kinds} classified; the dimension footnote is unreachable"


def test_the_counts_are_reported_so_drift_is_visible(entries, capsys):
    """Printed rather than asserted against a number: what these rates should be
    is a fact about the corpus, not something this suite gets to decide. A run
    that shows them moving is the signal worth having."""
    with capsys.disabled():
        print(f"\n{len(entries)} entries")
        for description, holds in MARKERS.items():
            count = sum(1 for entry in entries if holds(entry))
            print(f"  {count:>6}  {count / len(entries):6.1%}  {description}")
