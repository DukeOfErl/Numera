"""The question set is the reference every score is computed against.

So the tests are mostly about refusals. A set that loads when it should not is the
worst failure available here: every figure the evaluation reports afterwards is
wrong in a way that looks ordinary, and the run costs money before anyone reads it.
Each refusal below names the wrong figure it prevents.
"""

from __future__ import annotations

import json

import pytest

from scinumbers_ask.corpus import Entry
from scinumbers_ask.question_set import (
    EntryShape,
    Question,
    QuestionSetError,
    check_against_corpus,
    load_question_set,
    shapes_of,
)

SUPPORTED = {
    "question_id": "q1",
    "question": "How big is an E. coli cell?",
    "asked_property": "Cell volume",
    "asked_organism": "Bacteria Escherichia coli",
    "expected_entries": [100003, 100004],
    "tags": ["comparison"],
    "notes": "the classic",
}


def write_set(tmp_path, *records, name="questions.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return path


def an_entry(**kwargs) -> Entry:
    base = dict(
        entry_id=1,
        property="Cell volume",
        organism="Bacteria Escherichia coli",
        units="um^3",
        value=1.0,
        range_low=None,
        range_high=None,
        reference="r",
        reference_pubmed_id=None,
        measurement_method="electron microscopy",
        comments="",
        keywords=(),
    )
    base.update(kwargs)
    return Entry(**base)


# -- 2.1: the format ------------------------------------------------------------


def test_a_supported_question_reads_back_as_it_was_written(tmp_path):
    (question,) = load_question_set(write_set(tmp_path, SUPPORTED))
    assert question == Question(
        question_id="q1",
        question="How big is an E. coli cell?",
        asked_property="Cell volume",
        asked_organism="Bacteria Escherichia coli",
        expected_entries=(100003, 100004),
        unsupported=False,
        follows=None,
        tags=("comparison",),
        notes="the classic",
    )


def test_the_optional_keys_default_to_carrying_nothing(tmp_path):
    minimal = {key: SUPPORTED[key] for key in ("question_id", "question")}
    minimal.update(
        asked_property="Cell volume",
        asked_organism="Bacteria Escherichia coli",
        expected_entries=[100003],
    )
    (question,) = load_question_set(write_set(tmp_path, minimal))
    assert (question.tags, question.notes, question.follows) == ((), "", None)


def test_blank_lines_are_not_questions(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(f"\n{json.dumps(SUPPORTED)}\n\n")
    assert len(load_question_set(path)) == 1


def test_a_question_records_the_property_and_organism_it_asks(tmp_path):
    """Required, and not only for supported questions.

    Whether the agent searched for the asked organism is scored from these, so a
    question without them cannot be scored on the thing an answer most often gets
    wrong: a right number for the wrong organism.
    """
    for absent in ("asked_property", "asked_organism"):
        record = {key: value for key, value in SUPPORTED.items() if key != absent}
        with pytest.raises(QuestionSetError, match=absent):
            load_question_set(write_set(tmp_path, record))


def test_no_question_set_is_refused_with_an_explanation():
    """The refusal is on the loader, not the command.

    A harness, a test or a later driver calling this gets it too -- and one of them
    will, because the evaluation is meant to be run unattended.
    """
    with pytest.raises(QuestionSetError, match="No question set supplied"):
        load_question_set(None)
    with pytest.raises(QuestionSetError, match="No question set supplied"):
        load_question_set("")


def test_a_missing_or_empty_file_is_refused(tmp_path):
    with pytest.raises(QuestionSetError, match="No question set file"):
        load_question_set(tmp_path / "absent.jsonl")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n\n")
    with pytest.raises(QuestionSetError, match="holds no questions"):
        load_question_set(empty)


def test_a_line_that_is_not_json_names_its_line_number(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(json.dumps(SUPPORTED) + "\n{not json\n")
    with pytest.raises(QuestionSetError, match=r":2 is not valid JSON"):
        load_question_set(path)


def test_a_misspelled_key_is_refused_rather_than_ignored(tmp_path):
    """The failure this is here for: `expected_entires` silently read as absent.

    The question would then be scored against no expected entries, so a run in
    which the agent cited exactly the right entries reports as citing none of them
    -- and nothing in the output would say a key was misspelled.
    """
    record = {key: value for key, value in SUPPORTED.items() if key != "expected_entries"}
    record["expected_entires"] = [100003]
    with pytest.raises(QuestionSetError, match="expected_entires"):
        load_question_set(write_set(tmp_path, record))


def test_a_quoted_identifier_is_refused_rather_than_coerced(tmp_path):
    """`"100003"` never equals the `100003` a parsed citation carries.

    Coercing it here would work; refusing it is what stops the *other* direction,
    where a set written with quoted identifiers scores every citation as a miss
    forever and the comparison never fires.
    """
    with pytest.raises(QuestionSetError, match="bare integers"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "expected_entries": ["100003"]}))


def test_a_boolean_is_not_an_entry_identifier(tmp_path):
    """`isinstance(True, int)` is true, so `[true]` would become entry 1."""
    with pytest.raises(QuestionSetError, match="bare integers"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "expected_entries": [True]}))


def test_a_repeated_expected_entry_is_refused(tmp_path):
    """It would double the weight of one entry in every per-entry figure."""
    with pytest.raises(QuestionSetError, match="repeats"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "expected_entries": [100003, 100003]}))


def test_a_repeated_question_id_is_refused(tmp_path):
    """Results are keyed by it, so a repeat overwrites a result on resumption."""
    with pytest.raises(QuestionSetError, match="appears twice"):
        load_question_set(write_set(tmp_path, SUPPORTED, {**SUPPORTED, "question": "again?"}))


def test_a_field_of_the_wrong_type_is_refused(tmp_path):
    with pytest.raises(QuestionSetError, match="question must be a string"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "question": 7}))
    with pytest.raises(QuestionSetError, match="unsupported must be true or false"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "unsupported": "yes"}))
    with pytest.raises(QuestionSetError, match="tags must be a list"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "tags": "comparison"}))


def test_an_empty_question_is_refused(tmp_path):
    with pytest.raises(QuestionSetError, match="question is empty"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "question": "   "}))


# -- 2.2: unsupported questions and follow-ups ----------------------------------


def test_an_unsupported_question_names_no_expected_entries(tmp_path):
    unsupported = {
        "question_id": "q2",
        "question": "How many neoblasts does a planarian have?",
        "asked_property": "Number of neoblasts",
        "asked_organism": "Planarian",
        "unsupported": True,
        "tags": ["unsupported"],
    }
    (question,) = load_question_set(write_set(tmp_path, unsupported))
    assert question.unsupported and question.expected_entries == ()


def test_the_two_halves_of_the_unsupported_flag_are_refused_apart(tmp_path):
    """Different mistakes, and the fix for one is not the fix for the other."""
    with pytest.raises(QuestionSetError, match="marked unsupported but names expected"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "unsupported": True}))
    with pytest.raises(QuestionSetError, match="names no expected entries"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "expected_entries": []}))


def test_a_follow_up_records_the_question_it_follows(tmp_path):
    followup = {**SUPPORTED, "question_id": "q1b", "follows": "q1", "question": "and by mass?"}
    first, second = load_question_set(write_set(tmp_path, SUPPORTED, followup))
    assert (first.follows, second.follows) == (None, "q1")


def test_a_follow_up_naming_a_parent_the_set_does_not_hold_is_refused(tmp_path):
    """There would be no session to ask it in: a follow-up runs in its parent's."""
    followup = {**SUPPORTED, "question_id": "q1b", "follows": "q0"}
    with pytest.raises(QuestionSetError, match="follows 'q0', which the set does not"):
        load_question_set(write_set(tmp_path, SUPPORTED, followup))


def test_a_question_following_itself_is_refused(tmp_path):
    with pytest.raises(QuestionSetError, match="follows itself"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "follows": "q1"}))


def test_a_cycle_of_follow_ups_is_refused(tmp_path):
    """No question in it could be asked first, and walking the chain would not end."""
    a = {**SUPPORTED, "question_id": "qa", "follows": "qb"}
    b = {**SUPPORTED, "question_id": "qb", "follows": "qa"}
    with pytest.raises(QuestionSetError, match="cycle of follow-ups"):
        load_question_set(write_set(tmp_path, a, b))


def test_a_chain_of_follow_ups_is_allowed(tmp_path):
    """A cycle check that also refused a chain would be indistinguishable here."""
    a = {**SUPPORTED, "question_id": "qa"}
    b = {**SUPPORTED, "question_id": "qb", "follows": "qa"}
    c = {**SUPPORTED, "question_id": "qc", "follows": "qb"}
    assert len(load_question_set(write_set(tmp_path, a, b, c))) == 3


# -- 2.3: the shapes, derived from the corpus -----------------------------------


def test_an_entry_carrying_everything_is_complete():
    assert shapes_of(an_entry()) == frozenset({EntryShape.COMPLETE})


def test_an_entry_carries_every_shape_it_lacks_not_the_first_one_found():
    """One shape per entry would hide the second deficiency from every figure."""
    lacking_two = an_entry(value=None, range_low=1.0, range_high=2.0, measurement_method="")
    assert shapes_of(lacking_two) == frozenset({EntryShape.NO_SCALAR, EntryShape.NO_METHOD})


def test_a_deficiency_is_never_reported_as_complete():
    """The direction that matters: `COMPLETE` claims an entry a value check can
    be strict about, so it must never be produced alongside a deficiency."""
    for entry in (
        an_entry(value=None, range_low=1.0, range_high=2.0),
        an_entry(units="wibbles"),
        an_entry(units=""),
        an_entry(range_fused=True),
        an_entry(measurement_method="  "),
        an_entry(range_qualified=True, range_approximate=True),
    ):
        assert EntryShape.COMPLETE not in shapes_of(entry)


def test_each_deficiency_is_named_as_itself():
    assert EntryShape.NO_SCALAR in shapes_of(an_entry(value=None))
    assert EntryShape.NO_CLASSIFIED_UNIT in shapes_of(an_entry(units="wibbles"))
    assert EntryShape.NO_CLASSIFIED_UNIT in shapes_of(an_entry(units=""))
    assert EntryShape.FUSED_RANGE in shapes_of(an_entry(range_fused=True))
    assert EntryShape.NO_METHOD in shapes_of(an_entry(measurement_method=""))
    assert EntryShape.HEDGED_RANGE in shapes_of(an_entry(range_qualified=True))


def test_a_classified_unit_is_not_reported_as_missing():
    """The other direction of the unit rule: a unit the table knows must pass.

    `units.py` returns three values, and treating `unknown` and a real dimension
    alike here would file most of the corpus as unclassified and make the shape
    figures meaningless.
    """
    assert shapes_of(an_entry(units="um^3")) == frozenset({EntryShape.COMPLETE})
    assert EntryShape.NO_CLASSIFIED_UNIT not in shapes_of(an_entry(units="molecules/cell"))


def a_set_covering_every_shape() -> tuple[tuple[Question, ...], tuple[Entry, ...]]:
    entries = (
        an_entry(entry_id=1),
        an_entry(entry_id=2, value=None, range_low=1.0, range_high=2.0),
        an_entry(entry_id=3, units="wibbles"),
        an_entry(entry_id=4, range_fused=True),
        an_entry(entry_id=5, measurement_method=""),
        an_entry(entry_id=6, range_qualified=True, range_approximate=True),
    )
    questions = tuple(
        Question(
            question_id=f"q{entry.entry_id}",
            question="how big?",
            asked_property="Cell volume",
            asked_organism="Bacteria Escherichia coli",
            expected_entries=(entry.entry_id,),
        )
        for entry in entries
    )
    return questions, entries


def test_a_set_exercising_every_shape_passes_the_corpus_check():
    """The green baseline: without it, the two refusals below prove nothing."""
    questions, entries = a_set_covering_every_shape()
    check_against_corpus(questions, entries)


def test_a_set_of_complete_entries_alone_is_refused():
    """Most of the corpus is incomplete in at least one way, so a set drawn only
    from complete entries measures the happy path and reports nothing about the
    behaviour most questions will meet."""
    questions, entries = a_set_covering_every_shape()
    with pytest.raises(QuestionSetError, match="No question's expected entries carry"):
        check_against_corpus(questions[:1], entries)


def test_the_refusal_names_which_shapes_are_missing():
    questions, entries = a_set_covering_every_shape()
    with pytest.raises(QuestionSetError) as raised:
        check_against_corpus(questions[:2], entries)
    message = str(raised.value)
    assert "fused range" in message and "no measurement method" in message
    assert "no scalar value" not in message


def test_an_expected_entry_the_corpus_does_not_hold_is_refused():
    """A stale set after a corpus rebuild, or a typo. Either way nothing can be
    scored against the entry, and a run would report it as never retrieved."""
    questions, entries = a_set_covering_every_shape()
    stale = questions + (
        Question(
            question_id="q99",
            question="how big?",
            asked_property="Cell volume",
            asked_organism="Bacteria Escherichia coli",
            expected_entries=(999999,),
        ),
    )
    with pytest.raises(QuestionSetError, match=r"q99 expects \[999999\]"):
        check_against_corpus(stale, entries)


def test_an_unsupported_question_needs_no_entry_in_the_corpus():
    """It names none, so the absence check must not read it as a stale identifier."""
    questions, entries = a_set_covering_every_shape()
    with_unsupported = questions + (
        Question(
            question_id="q100",
            question="how many neoblasts?",
            asked_property="Number of neoblasts",
            asked_organism="Planarian",
            unsupported=True,
        ),
    )
    check_against_corpus(with_unsupported, entries)
