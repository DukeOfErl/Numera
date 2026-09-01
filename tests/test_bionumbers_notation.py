"""BioNumbers' own citation notation, and the parser that reads it.

The corpus's entry prose cites sibling entries as "See BNID 102065, 104333", and
that text is the source's words -- kept, not normalised. These tests cover the one
implementation that reads that notation, wherever it turns up: in an entry's prose,
and in an answer written after a reader introduced the form themselves.

Moved here verbatim from `test_entries_table.py` when the notation got its own
module. The expectations are unchanged; only what they are asserted against moved.
"""

from __future__ import annotations

import pytest

from scinumbers_ask.bionumbers import MIN_DIGITS, cross_references


def test_the_plural_marker_parses():
    """A model listing entries writes "BNIDs 100002" naturally. Parsed as uncited,
    that turned a well-cited answer into one with no citations at all: no cited rows,
    no unknown-or-unretrieved check, and a scorer recording zero."""
    assert cross_references("see BNIDs 100002") == (100002,)


def test_one_marker_introduces_a_run_of_identifiers():
    """The form the corpus's own entry text uses, and what a model listing entries
    writes unprompted. Both readings were in the codebase: the corpus parser read the
    run, the answer parser read only the first."""
    assert cross_references("see BNIDs 100002 and 100003") == (100002, 100003)
    assert cross_references("See BNID 102065, 104333") == (102065, 104333)
    assert cross_references("BNIDs 100002, 100003 & 100004") == (100002, 100003, 100004)


def test_a_run_stops_at_something_that_is_not_an_identifier():
    """Identifiers after the first are inferred from position, so each has to look
    like the first. Otherwise "and 3 other entries" contributes an entry 3, and the
    run's own tail is no longer trustworthy either."""
    assert cross_references("BNID 100002 and 3 other entries") == (100002,)
    assert cross_references("BNID 100002, 3, 100004") == (100002,)


def test_a_number_too_short_does_not_stop_the_rest_of_the_text_parsing():
    """Found by mutation testing: turning the skip into a stop survived every test.
    It would lose every citation after the first fragment, and an answer that did
    cite its entries would be reported as uncited."""
    assert cross_references("BNID 12 and BNID 100002") == (100002,)
    assert cross_references("see BNID 104 678, then BNID 100003") == (100003,)


def test_a_spaced_group_of_digits_does_not_contribute_an_identifier():
    """What MIN_DIGITS is for, stated as the requirement rather than as the number.

    A reference written "BNID 104 678" was contributing an entry 104 and an entry
    678, forty times over the corpus. The length floor is how that is suppressed,
    but the floor itself is a tuning constant, not a contract: no spec sets it, and
    the corpus runs 100001-117360, so a four-digit identifier cannot exist. An
    earlier version of this test asserted the exact boundary, which pinned the
    implementation's choice as though it were required -- and asserted that a
    four-digit citation is accepted, which is not behaviour worth guaranteeing.

    So mutation testing's survivor here (`<` widened to `<=`) is knowingly left
    alive. Killing it would mean testing the tuning rather than the requirement.
    """
    assert cross_references("see BNID 104 678") == ()
    assert cross_references("see BNID 104 678, then BNID 100003") == (100003,)


def test_a_number_too_short_to_be_an_identifier_is_refused():
    """34 entries write a cross-reference as "BNID 104 678". Reading the digits up to
    the space turns a citation this parser used to miss into a wrong one it reports
    with confidence, which is the worse of the two failures."""
    assert cross_references("see BNID 104 678") == ()
    assert len(str(cross_references("see BNID 104678")[0])) >= MIN_DIGITS


def test_a_bare_number_is_not_a_citation():
    """The reason the format is stated at all: a six-digit quantity is not an id."""
    assert cross_references("the cell holds 100000 ribosomes") == ()
    assert cross_references("100000 ribosomes (BNID 106576)") == (106576,)


@pytest.mark.parametrize(
    "text",
    ["BNID 100002", "bnid100002", "BNID: 100002", "bnid #100002", "BNID-100002"],
)
def test_the_marker_is_required_but_the_glue_is_not(text):
    """Permissive glue on purpose: this parser reads text nobody here wrote, so the
    form is a preference, not a control. A parser rejecting "BNID: x" would score a
    good answer as uncited, and a false negative is the worse error."""
    assert cross_references(text) == (100002,)


def test_identifiers_keep_their_order_without_repeating():
    # Realistic widths: identifiers below MIN_DIGITS are refused, because a
    # two-digit number after the marker is a fragment or a page, not an entry.
    assert cross_references("BNID 100003 then BNID 100001 then BNID 100003") == (
        100003,
        100001,
    )
