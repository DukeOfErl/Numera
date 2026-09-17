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

    SCINUMBERS_CORPUS=/path/to/corpus.jsonl uv run pytest -m corpus
"""

from __future__ import annotations

import os
from collections.abc import Callable

import pytest

from scinumbers_ask.corpus import Entry, load
from scinumbers_ask.entries_table import FUSED, IMPLAUSIBLE, NO_METHOD, NO_SCALAR, QUALIFIED
from scinumbers_ask.units import dimension

pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(
        not os.environ.get("SCINUMBERS_CORPUS"),
        reason="set SCINUMBERS_CORPUS to check the markers against a real corpus",
    ),
]

# Each marker beside the condition that raises it. Paired here so a reader can
# see what a mark on a row actually asserts, and so adding a marker without a
# line here is a visible omission rather than a silent one.
MARKERS: dict[str, Callable[[Entry], bool]] = {
    f"{NO_METHOD} no measurement method recorded": (lambda e: not e.measurement_method.strip()),
    f"{NO_SCALAR} no scalar value recorded": (
        lambda e: e.value is None and e.range_low is None and e.range_high is None
    ),
    "a unit the dimension table does not classify": lambda e: dimension(e.units) is None,
    f"{QUALIFIED} the source stated a bound, not an exact range": lambda e: e.range_qualified,
    f"{FUSED} the bounds may describe different quantities": lambda e: e.range_fused,
    f"{IMPLAUSIBLE} the bounds span more than a millionfold": lambda e: e.spans_implausibly,
    # Not marks of their own -- these two choose the words inside the value column,
    # "(approximate)" against "(a bound, not exact)". Counted here because they are
    # read by *name* out of the ingester's `parse_flags`, and that vocabulary is
    # explicitly its own to rename (its ADR-0230). A rename would turn both fields
    # False, and the value would quietly fall back to the vaguer wording with
    # nothing failing. This is what makes that loud.
    "range_approximate, which picks the word 'approximate'": lambda e: e.range_approximate,
    "range_one_sided, which picks 'a bound, not exact'": lambda e: e.range_one_sided,
}

# The first two are read from the corpus rather than computed here, which is the
# case this file exists for: a corpus that stops emitting a field leaves the mark
# silently undrawable, every test still passing, and the count reading zero as
# though the problem had gone away. That is precisely how the ingester's own
# markup flag read zero while 71 per cent of records were affected.

# Not here, and deliberately. The cited-but-not-retrieved mark is a property of an
# answer against what a question retrieved, not of an entry, so no corpus can say
# whether it fires. `tests/test_web_driver.py` and the terminal suite cover it
# against constructed answers, which is the only place it can be covered.


@pytest.fixture(scope="module")
def entries() -> tuple[Entry, ...]:
    return load(os.environ["SCINUMBERS_CORPUS"])


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


def test_the_two_hedge_kinds_together_account_for_every_qualified_entry(entries):
    """Measured, not assumed. If they stop partitioning `range_qualified`, either a
    flag was renamed or a third kind appeared -- and in both cases some hedged value
    is being described by the fallback wording rather than its own."""
    qualified = [e for e in entries if e.range_qualified]
    kinds = sum(1 for e in qualified if e.range_approximate or e.range_one_sided)
    both = sum(1 for e in qualified if e.range_approximate and e.range_one_sided)
    assert kinds == len(qualified), (
        f"{len(qualified) - kinds} qualified entries carry neither hedge kind, so they "
        "render with the fallback wording instead of saying which hedge the source used"
    )
    assert not both, f"{both} entries are both approximate and one-sided; the kinds overlap"


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


# -- which fields actually carry the source's notation -------------------


# Every text field of an entry that reaches the model. Listed here rather than
# derived, so adding a field to `Entry` without deciding whether it is restated is
# a visible omission -- the same reason MARKERS above is a literal table.
TEXT_FIELDS = (
    "property",
    "organism",
    "units",
    "reference",
    "reference_pubmed_id",
    "measurement_method",
    "comments",
)


def _fields_carrying_the_notation(entries) -> dict[str, int]:
    from scinumbers_ask.bionumbers import cross_references

    counts: dict[str, int] = {}
    for entry in entries:
        for field in TEXT_FIELDS:
            if cross_references(getattr(entry, field) or ""):
                counts[field] = counts.get(field, 0) + 1
    return counts


def test_the_notation_is_carried_by_fields_the_fixture_does_not_cover(entries):
    """Which fields really hold a cross-reference — measured, not assumed.

    This exists because a code review found what the suite could not: `rewrite` was
    applied to `comments` and `measurement_method`, and the six-entry fixture carries
    the marker only in `comments`. In the real corpus 8 entries cite others inside
    `property` and 2 inside `reference`, and `property` also reaches the model through
    `search_entries`. Every offline test passed.

    The fixture cannot answer this. It is six hand-picked entries, and ADR-0170 caps
    it deliberately, so it will never hold the distribution of shapes the source
    actually contains. Only counting against real data says which fields matter.

    Reported rather than asserted field by field: a new field appearing here is
    information, and the next test is what turns it into a failure.
    """
    counts = _fields_carrying_the_notation(entries)
    print("\nfields carrying the source's notation:")
    for field, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>6}  {field}")

    assert counts, "no entry cites another -- this check cannot fire, so it proves nothing"
    unexpected = set(counts) - {"comments", "measurement_method"}
    assert unexpected, (
        "only the two fields the fixture already covers carry the notation, so this "
        "check adds nothing over the offline suite -- verify against a full corpus"
    )


def test_no_field_hands_the_model_a_notation_it_is_not_asked_to_write(entries):
    """The requirement, over every entry that actually carries a cross-reference.

    `corpus-query`: the copy handed to the model restates the source's citations. The
    offline test asserts this on one entry; this asserts it on all of them, which is
    what catches a field nobody remembered to cover.

    Not "the marker is absent" — 40 entries write `BNID 100 004`, which the width
    floor refuses and which therefore passes through as the source's words, correctly.
    The claim is that no *readable* citation in the source's form survives.
    """
    from scinumbers_ask.bionumbers import cross_references
    from scinumbers_ask.repository import CorpusRepository
    from scinumbers_ask.tools import build_tools
    from scinumbers_ask.trace import QuestionTrace

    repo = CorpusRepository(entries)
    tools = {t.name: t for t in build_tools(repo, QuestionTrace("q"), lambda _e: None)}

    carrying = [
        e for e in entries if any(cross_references(getattr(e, f) or "") for f in TEXT_FIELDS)
    ]
    assert carrying, "no entry cites another -- this check cannot fire"

    leaked = []
    for entry in carrying:
        rendered = tools["get_entry"].invoke({"entry_id": entry.entry_id})
        if cross_references(rendered):
            leaked.append((entry.entry_id, cross_references(rendered)))

    assert not leaked, (
        f"{len(leaked)} of {len(carrying)} entries hand the model a citation in the "
        f"source's form; first few: {leaked[:5]}"
    )


# -- 5.5: what fraction of the corpus a value check could be strict about ----


#: The four conditions an entry has to meet for a stated value to be checkable
#: against it. Kept as a literal table, like MARKERS above, so adding a fifth is
#: a decision rather than a diff nobody reads.
CLEAN = {
    "a measurement method is recorded": lambda e: bool(e.measurement_method.strip()),
    "a scalar value is recorded": lambda e: e.value is not None,
    "the unit is classified": lambda e: dimension(e.units) is not None,
    "the range is not fused": lambda e: not e.range_fused,
}


def test_the_clean_fraction_is_reported_beside_the_answer_baseline(entries, capsys):
    """The base rate a citation rate has to be read against.

    Without it, "the agent cited a complete entry 14 per cent of the time" reads
    as a failure of the agent rather than as a fact about the corpus. Printed and
    not asserted, for the reason the marker counts are: what these rates *should*
    be is a fact about the corpus, and a test that pinned them would fail every
    time the ingester improved.

    **Reported twice, because one of the four conditions measures us and not the
    corpus.** An unclassified unit means `units.py`'s dimension table does not
    know that spelling -- which is our coverage, not the corpus's quality. So the
    conjunction is given once counting an unclassified unit as dirty and once
    treating it as unknown and setting it aside. The gap between the two figures
    is the size of our own table's blind spot, and on 2026-09-04 that table gained
    `kDalton` and seven per-cell counts, moving 73 entries.

    **Do not carry a figure from this test into a document without re-running it.**
    The fused-range population has been measured three times -- 1,716, then 1,222,
    then 1,445 -- because the ingester's number lexer was corrected twice. A flag
    is only ever as good as the tokenizer under it, and a rate quoted from memory
    is a rate measured against a lexer that no longer exists.
    """
    with capsys.disabled():
        print(f"\n{len(entries)} entries")
        for description, holds in CLEAN.items():
            count = sum(1 for entry in entries if holds(entry))
            print(f"  {count:>6}  {count / len(entries):6.1%}  {description}")

        strict = sum(1 for entry in entries if all(holds(entry) for holds in CLEAN.values()))
        print(f"  {strict:>6}  {strict / len(entries):6.1%}  all four (unclassified unit = dirty)")

        without_units = [holds for name, holds in CLEAN.items() if name != "the unit is classified"]
        lenient = sum(1 for entry in entries if all(holds(entry) for holds in without_units))
        print(f"  {lenient:>6}  {lenient / len(entries):6.1%}  the other three (unit set aside)")
        print(
            f"  {lenient - strict:>6}  {(lenient - strict) / len(entries):6.1%}  "
            f"the gap: our dimension table's blind spot, not the corpus's"
        )


def test_every_clean_condition_can_both_hold_and_fail(entries):
    """Each condition is a claim about the corpus, and a condition that never
    fails -- or never holds -- is reporting nothing while looking like a figure.

    Both directions, for the reason the marker tests check both: a rate of zero
    and a rate of one hundred per cent are the two ways a condition can be broken
    rather than informative.
    """
    for description, holds in CLEAN.items():
        met = sum(1 for entry in entries if holds(entry))
        assert 0 < met < len(entries), f"{description} holds for {met} of {len(entries)}"
