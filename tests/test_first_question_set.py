"""The committed question set, checked against a real corpus.

The set names entry identifiers, and a corpus is rebuilt from an export that is
itself revised. So the set can go stale in three ways -- an identifier that no
longer exists, a shape it no longer exercises, or an unsupported question the
corpus has since learned to answer -- and every one of them is silent: the run
still completes, and the figures are simply about something other than what the
set claims to measure.

Marked `corpus` and skipped by default, because this cannot be checked against the
six-entry fixture: that fixture holds two of the six entry shapes and no complete
entry at all, so a set that satisfied it would prove nothing about the real one.

    SCINUMBERS_CORPUS=/path/to/corpus.jsonl uv run pytest -m corpus
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scinumbers_ask.corpus import load
from scinumbers_ask.question_set import EntryShape, load_question_set, shapes_of

pytestmark = pytest.mark.corpus

FIRST_SET = Path(__file__).resolve().parents[1] / "question-sets" / "first-set.jsonl"


@pytest.fixture(scope="module")
def entries():
    configured = os.environ.get("SCINUMBERS_CORPUS")
    if not configured:
        pytest.skip("set SCINUMBERS_CORPUS to a real corpus")
    return load(configured)


def test_the_committed_set_still_validates_against_the_corpus(entries):
    """Every check `load_question_set` makes, on the set that will be run.

    That is the identifiers existing, all six shapes exercised, and no unsupported
    question the corpus can answer -- the last being the most expensive kind of
    staleness, since the agent would answer it correctly and be scored as having
    fabricated.
    """
    questions = load_question_set(FIRST_SET, entries)
    assert len(questions) >= 10


def test_the_set_holds_the_kinds_of_question_the_spec_requires(entries):
    """Composition, not just validity. A set can pass every structural check and
    still measure only the happy path."""
    questions = load_question_set(FIRST_SET, entries)
    assert any(question.unsupported for question in questions)
    assert any(question.follows is not None for question in questions)
    assert any(len(question.asked_organisms) > 1 for question in questions)
    tags = {tag for question in questions for tag in question.tags}
    assert {"classic", "unsupported", "follow-up", "comparison"} <= tags


def test_at_least_one_question_rests_only_on_complete_entries(entries):
    """The happy path has to exist as its own question, not merely as one entry
    inside a mixed one: the incomplete shapes are read against it."""
    held = {entry.entry_id: entry for entry in entries}
    questions = load_question_set(FIRST_SET, entries)
    assert any(
        question.expected_entries
        and all(
            shapes_of(held[identifier]) == frozenset({EntryShape.COMPLETE})
            for identifier in question.expected_entries
        )
        for question in questions
    )


# A phrase that marks an entry as measuring something *about* a quantity rather
# than the quantity itself. Not a parser -- a tripwire, in the exact shape the
# list has twice been rebuilt into and once been wrong about.
ALSO_RECORDS_IT = {
    # "Mass fraction of ribosome *and the number of ribosomes* in E. coli TG1 at
    # different phases of growth" -- a compound property that names a fraction and
    # records the count as well, so it is expected and the phrase list cannot tell.
    # Exempted by name with the reason rather than by blunting the rule, because
    # the rule's whole value is that it is sharp.
    105780,
}

DERIVED_OF = (
    "fraction of",
    "percentage of",
    "percent of",
    "ratio between",
    "ratios ",
    "per unit ",
    "standard deviation",
    "relative ",
)


def test_no_expected_entry_merely_names_the_quantity(entries):
    """The requirement says expected entries *record* the asked quantity, not that
    their property names it.

    A substring match on `property` selects "Fraction of nuclear volume out of cell
    volume" for a cell-volume question, and "Dry mass per unit cell volume", and
    "Ratio between diploid/haploid cell volume". None of them records a cell
    volume. The lists were built by hand for exactly this reason, and this fires if
    anyone later rebuilds them with a query -- which is how they were wrong the
    first time.

    Anything genuinely answering the question by a short derivation belongs in
    `admissible_entries`, which this deliberately does not check.
    """
    held = {entry.entry_id: entry for entry in entries}
    offenders = []
    for question in load_question_set(FIRST_SET, entries):
        for identifier in question.expected_entries:
            if identifier in ALSO_RECORDS_IT:
                continue
            name = held[identifier].property.lower()
            hit = next((phrase for phrase in DERIVED_OF if phrase in name), None)
            if hit:
                offenders.append(f"{question.question_id}: {identifier} ({hit!r}) {name[:60]}")
    assert not offenders, (
        "expected entries that measure something about the quantity:\n  " + "\n  ".join(offenders)
    )
