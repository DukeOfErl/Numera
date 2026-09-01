"""The form the model is asked to write, and how it is read back.

Delimited, so nothing here infers where an identifier ends. The rules the previous
notation needed -- a width floor, a run heuristic, a same-number-of-digits
continuation -- are gone from this path; they live in `bionumbers.py`, which reads
a notation that marks only where an identifier begins.
"""

from __future__ import annotations

import io
import json

from scinumbers_ask import bionumbers
from scinumbers_ask.agent import SYSTEM_PROMPT
from scinumbers_ask.citations import FORM, citations, format_citation
from scinumbers_ask.trace import configure, start_question


def records(buf: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


# -- the delimited form ---------------------------------------------------


def test_the_written_form_is_the_form_that_parses():
    """Otherwise the prompt, the drivers and the scorer could drift apart."""
    assert citations(format_citation(100002)) == (100002,)
    assert citations(FORM) == (100002,)


def test_the_prompt_asks_for_the_form_this_module_parses():
    """The prompt restated the form as a literal for the project's whole life, with
    nothing tying the two together. It could have asked for a notation the parser did
    not read, and the only symptom would have been every answer reported as uncited."""
    assert FORM in SYSTEM_PROMPT


def test_a_bare_number_is_not_a_citation():
    """The reason a form is stated at all: a six-digit quantity is not an identifier."""
    assert citations("the cell holds 100000 ribosomes") == ()


def test_identifiers_keep_their_order_without_repeating():
    assert citations("[[100003]] then [[100001]] then [[100003]]") == (100003, 100001)


def test_no_width_floor_and_no_run_rule_apply_to_this_form():
    """What the delimiters buy. The previous notation could not tell "BNID 100002 and
    3 other entries" from a run, so it needed a rule about digits; a closing delimiter
    says where the identifier ends, so a short identifier is just an identifier and an
    adjacent number is just a number."""
    assert citations("[[12]] and 3 other entries") == (12,)
    assert citations("[[100002]] and 3 other entries") == (100002,)


def test_a_bracket_group_holding_no_identifier_is_recorded_not_dropped():
    """A model trying to cite and failing is worth knowing about, and is invisible
    otherwise: the answer simply reads as uncited, indistinguishable from one that
    never tried. Silence here would retire the suspicion that finds the problem."""
    buf = io.StringIO()
    configure(buf)
    trace = start_question("dev")

    assert citations("as reported in [[the source]]", trace=trace) == ()

    unparsable = [r for r in records(buf) if r["event"] == "citations.unparsable"]
    assert len(unparsable) == 1
    assert "the source" in json.dumps(unparsable[0])


def test_a_model_bracketing_more_than_the_number_is_still_read():
    """A plausible hedge from a model shown the source's form in an entry's prose.
    Dropping it would lose a citation a reader can plainly see."""
    assert citations("[[BNID 100002]]") == (100002,)
    assert citations("[[ 100002 ]]") == (100002,)


# -- the source's form is tolerated too -----------------------------------


def test_the_source_form_is_accepted_in_an_answer():
    """Not because the model invents it -- an entry rendered to the model no longer
    contains it -- but because a reader who knows the database types it in their own
    question, and a session's follow-ups inherit the conversation. Once it is in the
    transcript the model answers in it, and a delimited-only parser would mark every
    one of those well-cited answers unsupported."""
    assert citations("about 1 micrometre (BNID 100002)") == (100002,)
    assert citations("see BNIDs 100002 and 100003") == (100002, 100003)


def test_the_two_notations_are_ordered_by_where_they_appear():
    """Not one appended to the other. Concatenating would put a citation the reader
    met first after every citation written the other way, and the entries table shows
    rows in the order the answer cites them."""
    assert citations("[[100003]] and BNID 100001") == (100003, 100001)
    assert citations("BNID 100001 and [[100003]]") == (100001, 100003)


def test_one_implementation_reads_the_source_form():
    """Two parsers for one notation drifted once already. There are two callers now,
    which is the point of the split; a second implementation is not."""
    from scinumbers_ask import citations as citations_module

    assert citations_module.cross_references is bionumbers.cross_references
