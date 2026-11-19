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

from numera_ask import bionumbers
from numera_ask.bionumbers import MIN_DIGITS, cross_references, label, rewrite
from numera_ask.citations import format_citation


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
    alive -- in `occurrences` and, since the notation grew a second reader, in
    `rewrite` too. Killing either would mean testing the tuning rather than the
    requirement.
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


# -- restating the notation when the model is handed an entry -------------


def test_a_run_is_restated_with_every_identifier_delimited():
    """The whole reason this exists: "See BNID 102065, 104333" shown to a model that
    was asked for one identifier per pair of brackets."""
    assert rewrite("See BNID 102065, 104333", format_citation) == "See [[102065]], [[104333]]"
    assert rewrite("BNIDs 100002, 100003 & 100004", format_citation) == (
        "[[100002]], [[100003]] & [[100004]]"
    )


def test_what_is_not_an_identifier_is_left_exactly_as_the_source_wrote_it():
    """A rendering, never a repair. "BNID 104 678" fails the width floor, so it passes
    through untouched rather than being half-converted into a citation the source never
    made -- and the trailing number in a run is left alone for the same reason."""
    assert rewrite("see BNID 104 678", format_citation) == "see BNID 104 678"
    assert rewrite("BNID 100002 and 3 other entries", format_citation) == (
        "[[100002]] and 3 other entries"
    )
    assert rewrite("no citation here", format_citation) == "no citation here"
    assert rewrite("", format_citation) == ""


def test_the_corpus_keeps_the_sources_words_and_the_model_gets_ours(repo):
    """ADR-0420. Three surfaces, and only the model's is restated: the stored entry is
    the source's evidence, the reader is owed the attribution, and the model is owed one
    notation. Normalising at ingest would have collapsed all three into ours."""
    from numera_ask.tools import build_tools
    from numera_ask.trace import QuestionTrace

    stored = repo.get(100001).entry
    assert "BNID 102065" in stored.comments, "the corpus must keep the source's words"

    tools = {t.name: t for t in build_tools(repo, QuestionTrace("q"), lambda _e: None)}
    rendered = tools["get_entry"].invoke({"entry_id": 100001})
    assert "[[102065]]" in rendered
    # No *readable* cross-reference survives -- not "the marker is absent". 101 real
    # entries write one as "BNID 100 004", which the width floor refuses and which
    # therefore passes through as the source's words, correctly. Asserting the marker
    # is gone would be asserting something the real corpus does not satisfy, which the
    # six-entry fixture was hiding.
    assert cross_references(rendered) == (), "no citation in the source's form may remain"


def test_a_person_is_told_which_database_the_identifier_belongs_to():
    """The display is attribution, not a citation protocol. A reader looking at a
    BioNumbers entry is told it is a BNID; the model's form says nothing about which
    database an entry came from, and would be the wrong thing to show."""
    assert label(100002) == "BNID 100002"
    assert format_citation(100002) != label(100002)


def test_the_source_marker_appears_in_no_other_module():
    """ "Not everywhere -- only where BioNumbers is the one speaking." Comments and
    docstrings may cite real entries as evidence; what must not spread is the marker in
    a string the program actually uses, because that is a second place the notation
    would have to be changed and the first place it would be forgotten.
    """
    import ast
    import pathlib

    package = pathlib.Path(bionumbers.__file__).parent
    offenders = {}
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                first = node.body[0] if node.body else None
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docstrings.add(id(first.value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and "BNID" in node.value
            ):
                offenders.setdefault(path.name, []).append(node.value[:60])

    assert set(offenders) <= {"bionumbers.py"}, offenders


def test_every_field_handed_to_the_model_is_restated_not_just_the_obvious_two(tmp_path):
    """`comments` and `method` are not the only fields carrying the marker.

    In the real corpus 8 entries cite others inside `property` and 2 inside
    `reference`, and `property` reaches the model through `search_entries` as well.
    Restating field by field is a list someone has to keep complete; this asserts the
    boundary instead, so a field added later cannot quietly escape.
    """
    import json

    from numera_ask.corpus import load
    from numera_ask.repository import CorpusRepository
    from numera_ask.tools import build_tools
    from numera_ask.trace import QuestionTrace

    record = {
        "entry_id": 101734,
        "property": "Number of skin cells (for total number of cells, see BNIDS 113005, 113006)",
        "organism": "Human",
        "units": "cells",
        "value": 1.0,
        "range_low": None,
        "range_high": None,
        "reference": "Calculated using Human genome size (BNID 101484)",
        "reference_pubmed_id": None,
        "measurement_method": "",
        "comments": "",
        "keywords": [],
    }
    path = tmp_path / "corpus.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    repo = CorpusRepository(load(path))
    tools = {t.name: t for t in build_tools(repo, QuestionTrace("q"), lambda _e: None)}

    entry = tools["get_entry"].invoke({"entry_id": 101734})
    assert cross_references(entry) == (), f"the source's form survived in:\n{entry}"
    assert "[[113005]]" in entry and "[[101484]]" in entry

    listing = tools["search_entries"].invoke({"property": "skin cells"})
    assert cross_references(listing) == (), f"the source's form survived in:\n{listing}"


def test_a_lone_citation_is_restated_and_nothing_else_changes():
    """Found by mutation testing: with no run after the identifier the trailing group
    is empty, and a mutant replacing that empty string with a sentinel appended it to
    the output -- surviving every test, because each one asserted the identifier was
    *present* rather than asserting the whole string.

    2 real entries carry a lone cross-reference in `reference`, so this is the shape
    that reaches the model unasserted. Exact equality, since ADR-0420's claim is that
    the citation is restated and the source's other words are not touched.
    """
    assert rewrite("(BNID 101484)", format_citation) == "([[101484]])"
    assert rewrite("BNID 100002", format_citation) == "[[100002]]"
    assert rewrite("as reported in BNID 100002.", format_citation) == "as reported in [[100002]]."
