"""The question set is the reference every score is computed against.

So the tests are mostly about refusals. A set that loads when it should not is the
worst failure available here: every figure the evaluation reports afterwards is
wrong in a way that looks ordinary, and the run costs money before anyone reads it.
Each refusal below names the wrong figure it prevents.

**Ten mutants are knowingly left alive**, out of 327 over `question_set.py`
(2026-09-04, after the branch review). Nine rewrite the prose inside an error
message -- upper-casing a sentence, wrapping it in sentinels, changing the `"; "`
that joins a list. Killing them would mean asserting every sentence in full, which
pins wording as contract and makes the messages unimprovable. The tenth spells the
encoding `"UTF-8-SIG"`, which is the same codec.

What the runs found that was real, all tested below: every location argument could
be replaced with `None`, so every refusal could have said "None: ..." with the
suite still green; the duplicate-id message counted questions rather than lines,
which sends a reader to the wrong line the moment the file holds a blank one; and
each path the review's fixes added arrived with its own message unasserted, which
is worth expecting -- new code brings new mutants, so a second run after a rework
is not a formality.
"""

from __future__ import annotations

import json

import pytest
from conftest import FIXTURE, write_all_shapes_corpus

from scinumbers_ask.corpus import Entry, load
from scinumbers_ask.question_set import (
    EntryShape,
    Question,
    QuestionSetError,
    Tier,
    check_against_corpus,
    load_question_set,
    shapes_of,
)

SUPPORTED = {
    "question_id": "q1",
    "question": "How big is an E. coli cell?",
    "asked_properties": "Cell volume",
    "asked_organisms": "Bacteria Escherichia coli",
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
    (question,) = load_question_set(write_set(tmp_path, SUPPORTED), None)
    assert question == Question(
        question_id="q1",
        question="How big is an E. coli cell?",
        asked_properties=("Cell volume",),
        asked_organisms=("Bacteria Escherichia coli",),
        expected_entries=(100003, 100004),
        unsupported=False,
        follows=None,
        tags=("comparison",),
        notes="the classic",
    )


def test_the_optional_keys_default_to_carrying_nothing(tmp_path):
    minimal = {key: SUPPORTED[key] for key in ("question_id", "question")}
    minimal.update(
        asked_properties=("Cell volume",),
        asked_organisms=("Bacteria Escherichia coli",),
        expected_entries=[100003],
    )
    (question,) = load_question_set(write_set(tmp_path, minimal), None)
    assert (question.tags, question.notes, question.follows) == ((), "", None)


def test_blank_lines_are_not_questions(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(f"\n{json.dumps(SUPPORTED)}\n\n")
    assert len(load_question_set(path, None)) == 1


def test_a_question_records_the_property_and_organism_it_asks(tmp_path):
    """Required, and not only for supported questions.

    Whether the agent searched for the asked organism is scored from these, so a
    question without them cannot be scored on the thing an answer most often gets
    wrong: a right number for the wrong organism.
    """
    unsupported = {
        "question_id": "q2",
        "question": "How many neoblasts does a planarian have?",
        "asked_properties": "Number of neoblasts",
        "asked_organisms": "Planarian",
        "unsupported": True,
    }
    for complete in (SUPPORTED, unsupported):
        for absent in ("asked_properties", "asked_organisms"):
            record = {key: value for key, value in complete.items() if key != absent}
            with pytest.raises(QuestionSetError, match=absent):
                load_question_set(write_set(tmp_path, record), None)


def test_no_question_set_is_refused_with_an_explanation():
    """The refusal is on the loader, not the command.

    A harness, a test or a later driver calling this gets it too -- and one of them
    will, because the evaluation is meant to be run unattended.
    """
    with pytest.raises(QuestionSetError, match="No question set supplied"):
        load_question_set(None, None)
    with pytest.raises(QuestionSetError, match="No question set supplied"):
        load_question_set("", None)


def test_a_missing_or_empty_file_is_refused(tmp_path):
    with pytest.raises(QuestionSetError, match="No question set file"):
        load_question_set(tmp_path / "absent.jsonl", None)
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n\n")
    with pytest.raises(QuestionSetError, match="holds no questions"):
        load_question_set(empty, None)


def test_a_line_that_is_json_but_not_an_object_is_refused(tmp_path):
    """A set written as one JSON array, or a stray string, reaches here as a valid
    line that is not a question. Without this the reader would fail later, on a
    missing key, and blame the question rather than the shape of the file."""
    path = tmp_path / "questions.jsonl"
    path.write_text("[1, 2]\n")
    with pytest.raises(QuestionSetError, match="is not a JSON object"):
        load_question_set(path, None)


def test_the_type_a_field_was_given_is_named_in_the_refusal(tmp_path):
    """ "must be a string" says what was wanted; the reader also needs what they
    wrote, or a `7` and a `"7"` produce the same message."""
    with pytest.raises(QuestionSetError, match="must be a string, not int"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "question": 7}), None)


def test_a_line_that_is_not_json_names_its_line_number(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(json.dumps(SUPPORTED) + "\n{not json\n")
    with pytest.raises(QuestionSetError, match=r":2 is not valid JSON"):
        load_question_set(path, None)


def test_a_misspelled_key_is_refused_rather_than_ignored(tmp_path):
    """The failure this is here for: `expected_entires` silently read as absent.

    The question would then be scored against no expected entries, so a run in
    which the agent cited exactly the right entries reports as citing none of them
    -- and nothing in the output would say a key was misspelled.
    """
    record = {key: value for key, value in SUPPORTED.items() if key != "expected_entries"}
    record["expected_entires"] = [100003]
    with pytest.raises(QuestionSetError, match="expected_entires"):
        load_question_set(write_set(tmp_path, record), None)


def test_a_quoted_identifier_is_refused_rather_than_coerced(tmp_path):
    """`"100003"` never equals the `100003` a parsed citation carries.

    Coercing it here would work; refusing it is what stops the *other* direction,
    where a set written with quoted identifiers scores every citation as a miss
    forever and the comparison never fires.
    """
    with pytest.raises(QuestionSetError, match="bare integers"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "expected_entries": ["100003"]}), None)


def test_a_boolean_is_not_an_entry_identifier(tmp_path):
    """`isinstance(True, int)` is true, so `[true]` would become entry 1."""
    with pytest.raises(QuestionSetError, match="bare integers"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "expected_entries": [True]}), None)


def test_a_repeated_expected_entry_is_refused(tmp_path):
    """It would double the weight of one entry in every per-entry figure."""
    with pytest.raises(QuestionSetError, match="repeats"):
        load_question_set(
            write_set(tmp_path, {**SUPPORTED, "expected_entries": [100003, 100003]}), None
        )


@pytest.mark.parametrize(
    "broken",
    [
        {"question": 7},
        {"expected_entries": "100003"},
        {"unsupported": "yes"},
        {"tags": [""]},
        {"notes": 3},
        {"asked_organisms": ""},
        {"follows": 4},
        {"nonsense": 1},
        {"question_id": 7},
        {"asked_properties": [4]},
        {"asked_properties": []},
    ],
    ids=[
        "question",
        "expected_entries",
        "unsupported",
        "tags",
        "notes",
        "asked_organisms",
        "follows",
        "unknown key",
        "question_id",
        "a term of the wrong type",
        "no terms at all",
    ],
)
def test_every_refusal_names_the_file_and_the_line_it_is_on(tmp_path, broken):
    """A set is a file a person edits, and a refusal it cannot be acted on is half a
    refusal. This module's own docstring promises "a message naming the line and the
    fix", and until mutation testing asked, nothing held the first half: every
    location argument could be replaced with `None` -- turning every message into
    "None: ..." -- and all 38 tests still passed.

    The bad question is deliberately the second line, so a message that named the
    first line by accident would fail this too.
    """
    path = write_set(tmp_path, SUPPORTED, {**SUPPORTED, "question_id": "q2", **broken})
    with pytest.raises(QuestionSetError) as raised:
        load_question_set(path, None)
    assert f"{path}:2" in str(raised.value)


def test_a_key_named_in_a_refusal_is_the_key_that_was_wrong(tmp_path):
    """`follows` and `notes` are reported through the same helper as every other
    field, so the key it is given is what tells the reader which one to fix."""
    with pytest.raises(QuestionSetError, match="follows must be a string"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "follows": 4}), None)
    with pytest.raises(QuestionSetError, match="notes must be a string"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "notes": 4}), None)
    with pytest.raises(QuestionSetError, match="tag is empty"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "tags": [""]}), None)
    with pytest.raises(QuestionSetError, match="question_id must be a string"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "question_id": 7}), None)
    with pytest.raises(QuestionSetError, match="asked_properties must be a string"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "asked_properties": [4]}), None)
    with pytest.raises(QuestionSetError, match="asked_organisms is empty"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "asked_organisms": []}), None)


def test_a_repeated_question_id_is_refused_and_both_lines_are_named(tmp_path):
    """Results are keyed by it, so a repeat overwrites a result on resumption.

    Both locations, and as lines rather than as ordinals among the questions. The
    two diverge the moment the file has a blank line in it, and a message saying
    "questions 1 and 2" sends the reader to the wrong pair of lines -- which is
    what this said until an `enumerate(start=1)` mutant survived and raised it.
    """
    path = tmp_path / "questions.jsonl"
    path.write_text(
        "\n".join(["", json.dumps(SUPPORTED), "", json.dumps({**SUPPORTED, "question": "again?"})])
        + "\n"
    )
    with pytest.raises(QuestionSetError) as raised:
        load_question_set(path, None)
    assert f"at {path}:2 and {path}:4" in str(raised.value)


def test_a_field_of_the_wrong_type_is_refused(tmp_path):
    with pytest.raises(QuestionSetError, match="question must be a string"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "question": 7}), None)
    with pytest.raises(QuestionSetError, match="unsupported must be true or false"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "unsupported": "yes"}), None)
    with pytest.raises(QuestionSetError, match="tags must be a list"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "tags": "comparison"}), None)


def test_an_empty_question_is_refused(tmp_path):
    with pytest.raises(QuestionSetError, match="question is empty"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "question": "   "}), None)


# -- 2.2: unsupported questions and follow-ups ----------------------------------


def test_an_unsupported_question_names_no_expected_entries(tmp_path):
    unsupported = {
        "question_id": "q2",
        "question": "How many neoblasts does a planarian have?",
        "asked_properties": "Number of neoblasts",
        "asked_organisms": "Planarian",
        "unsupported": True,
        "tags": ["unsupported"],
    }
    (question,) = load_question_set(write_set(tmp_path, unsupported), None)
    assert question.unsupported and question.expected_entries == ()


def test_the_two_halves_of_the_unsupported_flag_are_refused_apart(tmp_path):
    """Different mistakes, and the fix for one is not the fix for the other."""
    with pytest.raises(QuestionSetError, match="marked unsupported but names expected"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "unsupported": True}), None)
    with pytest.raises(QuestionSetError, match="neither expected nor admissible"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "expected_entries": []}), None)


def test_a_follow_up_records_the_question_it_follows(tmp_path):
    followup = {**SUPPORTED, "question_id": "q1b", "follows": "q1", "question": "and by mass?"}
    first, second = load_question_set(write_set(tmp_path, SUPPORTED, followup), None)
    assert (first.follows, second.follows) == (None, "q1")


def test_a_follow_up_naming_a_parent_the_set_does_not_hold_is_refused(tmp_path):
    """There would be no session to ask it in: a follow-up runs in its parent's."""
    followup = {**SUPPORTED, "question_id": "q1b", "follows": "q0"}
    path = write_set(tmp_path, SUPPORTED, followup)
    with pytest.raises(QuestionSetError) as raised:
        load_question_set(path, None)
    assert "follows 'q0', which the set does not" in str(raised.value)
    assert f"{path}:2" in str(raised.value)


def test_a_question_following_itself_is_refused(tmp_path):
    with pytest.raises(QuestionSetError, match="follows itself"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "follows": "q1"}), None)


def test_a_cycle_of_follow_ups_is_refused(tmp_path):
    """No question in it could be asked first, and walking the chain would not end."""
    a = {**SUPPORTED, "question_id": "qa", "follows": "qb"}
    b = {**SUPPORTED, "question_id": "qb", "follows": "qa"}
    path = write_set(tmp_path, a, b)
    with pytest.raises(QuestionSetError) as raised:
        load_question_set(path, None)
    assert "cycle of follow-ups" in str(raised.value)
    assert f"{path}:1" in str(raised.value)


def test_a_chain_of_follow_ups_is_allowed(tmp_path):
    """A cycle check that also refused a chain would be indistinguishable here."""
    a = {**SUPPORTED, "question_id": "qa"}
    b = {**SUPPORTED, "question_id": "qb", "follows": "qa"}
    c = {**SUPPORTED, "question_id": "qc", "follows": "qb"}
    assert len(load_question_set(write_set(tmp_path, a, b, c), None)) == 3


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

    `dimension()` answers with a name or `None`, and treating an unclassified unit
    and a real dimension alike here would file most of the corpus as unclassified
    and make the shape figures meaningless. (`comparable()` is the three-valued
    one; this reads the two-valued `dimension`.)
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
            asked_properties=("Cell volume",),
            asked_organisms=("Bacteria Escherichia coli",),
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
            asked_properties=("Cell volume",),
            asked_organisms=("Bacteria Escherichia coli",),
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
            asked_properties=("Number of neoblasts",),
            asked_organisms=("Planarian",),
            unsupported=True,
        ),
    )
    check_against_corpus(with_unsupported, entries)


# -- What the branch review found ------------------------------------------------


def test_a_parent_that_is_itself_dangling_is_refused_not_a_traceback(tmp_path):
    """The bug this holds: a *grandparent* nobody had checked.

    Each question's own parent was checked as the cycle walk reached it, which left
    the walk free to step through an ancestor that was never checked. Reading `qa`
    first, the walk went qa -> qb -> qZ and dereferenced qZ, raising `KeyError` --
    reported by the command as a traceback, the one outcome the command exists to
    prevent. Reversing the two lines gave the correct refusal, so the failure
    depended on the order of the file.
    """
    a = {**SUPPORTED, "question_id": "qa", "follows": "qb"}
    b = {**SUPPORTED, "question_id": "qb", "follows": "qZ"}
    with pytest.raises(QuestionSetError, match="follows 'qZ', which the set does not"):
        load_question_set(write_set(tmp_path, a, b), None)


@pytest.mark.parametrize("flag", ["range_qualified", "range_approximate", "range_one_sided"])
def test_any_hedge_flag_alone_marks_a_hedged_range(flag):
    """Three independent booleans, and `corpus.py` reads them as three.

    It is the ingester that derives the general flag from the two specific ones, so
    a corpus carrying `range_approximate` without `range_qualified` loads perfectly
    well. Reading only the general flag filed a value of "~20" as `COMPLETE` -- an
    entry a value check would then be strict about, which is the expensive
    direction.
    """
    shapes = shapes_of(an_entry(**{flag: True}))
    assert EntryShape.HEDGED_RANGE in shapes
    assert EntryShape.COMPLETE not in shapes


def test_tags_are_stripped_and_a_repeat_is_refused(tmp_path):
    """The report groups its figures by tag, so a repeat counts one question twice
    in its own bucket -- the reasoning that already deduplicates expected entries."""
    (question,) = load_question_set(
        write_set(tmp_path, {**SUPPORTED, "tags": ["  comparison  ", "conversion"]}), None
    )
    assert question.tags == ("comparison", "conversion")
    with pytest.raises(QuestionSetError, match="tags repeat 'comparison'"):
        load_question_set(write_set(tmp_path, {**SUPPORTED, "tags": ["comparison"] * 2}), None)


def test_two_tags_differing_only_in_case_are_refused(tmp_path):
    """They would make two buckets a reader then compares against each other. The
    vocabulary is free-form, so there is nothing to check a tag against -- but
    being distinct needs no vocabulary."""
    with pytest.raises(QuestionSetError, match="differ only in case"):
        load_question_set(
            write_set(tmp_path, {**SUPPORTED, "tags": ["comparison", "Comparison"]}), None
        )


def test_a_comparison_question_records_every_organism_it_asks_about(tmp_path):
    """ "Is an E. coli cell bigger than a yeast cell?" asks about two organisms.

    With one term per question, the requirement `The asked property and organism
    are recognised` would score a perfect answer to this question at half: the
    fraction of cited entries carrying "the asked organism" cannot exceed 50% when
    half the entries are the other organism. The spec names a comparison across
    entries as a tag the set carries, so the format has to hold both.
    """
    comparison = {
        **SUPPORTED,
        "question": "Is an E. coli cell bigger than a yeast cell?",
        "asked_organisms": ["Bacteria Escherichia coli", "Fungi Saccharomyces cerevisiae"],
        "tags": ["comparison"],
    }
    (question,) = load_question_set(write_set(tmp_path, comparison), None)
    assert question.asked_organisms == (
        "Bacteria Escherichia coli",
        "Fungi Saccharomyces cerevisiae",
    )
    assert question.asked_properties == ("Cell volume",)


def test_the_same_organism_asked_twice_is_refused(tmp_path):
    """A repeat would weight one organism twice in the per-question fraction."""
    with pytest.raises(QuestionSetError, match="asked_organisms repeats"):
        load_question_set(
            write_set(tmp_path, {**SUPPORTED, "asked_organisms": ["yeast", "yeast"]}), None
        )


def test_a_question_built_in_code_carries_the_same_invariants_as_one_read(tmp_path):
    """Groups 3 to 6 build these in fixtures, and the reader is not the only caller.

    A `Question` with neither an unsupported flag nor expected entries scores as
    "cited 0 of 0 expected", which reads as a pass rather than as a broken set --
    so the type refuses it, not only the file reader.
    """
    valid = dict(
        question_id="q1",
        question="how big?",
        asked_properties=("Cell volume",),
        asked_organisms=("Bacteria Escherichia coli",),
    )
    with pytest.raises(QuestionSetError, match="neither expected nor admissible"):
        Question(**valid)
    # The third state: admissible entries alone are support enough, because a
    # false-premise question has no expected entry and is not unsupported either.
    Question(**valid, admissible_entries=(1,))
    with pytest.raises(QuestionSetError, match="unsupported and names expected entries"):
        Question(**valid, unsupported=True, expected_entries=(1,))
    with pytest.raises(QuestionSetError, match="no asked property or organism"):
        Question(**{**valid, "asked_organisms": ()}, expected_entries=(1,))
    with pytest.raises(QuestionSetError, match="needs an identifier and a question"):
        Question(**{**valid, "question": ""}, expected_entries=(1,))
    with pytest.raises(QuestionSetError, match="follows itself"):
        Question(**valid, expected_entries=(1,), follows="q1")


def test_a_byte_order_mark_does_not_make_a_set_unreadable(tmp_path):
    """The commonest editors on Windows write one, and `utf-8` rejects it with
    "Unexpected UTF-8 BOM" -- a first impression paid for nothing, since
    `utf-8-sig` reads a plain UTF-8 file identically."""
    path = tmp_path / "questions.jsonl"
    path.write_text(json.dumps(SUPPORTED) + "\n", encoding="utf-8-sig")
    assert len(load_question_set(path, None)) == 1


def test_padded_text_is_stripped_so_it_matches_what_names_it(tmp_path):
    """A padded identifier would not match the `follows` naming it, and a padded
    organism term would reach the repository's resolution with its spaces."""
    parent = {**SUPPORTED, "question_id": "  qa  ", "asked_organisms": "  yeast  "}
    child = {**SUPPORTED, "question_id": "qb", "follows": "qa"}
    first, second = load_question_set(write_set(tmp_path, parent, child), None)
    assert first.question_id == "qa"
    assert first.asked_organisms == ("yeast",)
    assert second.follows == "qa"


def test_the_cycle_message_names_the_cycle_and_not_the_walk(tmp_path):
    """Where A follows B follows C follows B, the cycle is B and C. Naming A in it
    sends the reader to the one question in the chain that is fine."""
    a = {**SUPPORTED, "question_id": "qa", "follows": "qb"}
    b = {**SUPPORTED, "question_id": "qb", "follows": "qc"}
    c = {**SUPPORTED, "question_id": "qc", "follows": "qb"}
    with pytest.raises(QuestionSetError) as raised:
        load_question_set(write_set(tmp_path, a, b, c), None)
    message = str(raised.value)
    assert "'qb', 'qc'" in message and "'qa'," not in message


def test_a_set_read_from_a_file_can_satisfy_the_corpus_check(tmp_path):
    """The passing path end to end: reader, then corpus, on real files.

    Every other test of the shape rule constructs its `Question`s and `Entry`s in
    code, so none of them checks that a set written as a file can satisfy it. That
    is the doubles-hide-the-real-path shape the project's coverage note warns
    about.
    """
    corpus = load(write_all_shapes_corpus(tmp_path))
    questions = [
        {**SUPPORTED, "question_id": f"q{identifier}", "expected_entries": [identifier]}
        for identifier in range(1, 7)
    ]
    loaded = load_question_set(write_set(tmp_path, *questions), corpus)
    assert len(loaded) == 6


def test_the_corpus_check_runs_when_the_loader_is_given_a_corpus(tmp_path):
    """The guard is on the operation, not on the command.

    The corpus check used to be a second function the only caller invoked behind an
    `if`. The evaluation driver always has a corpus, so it must not be able to skip
    the check by leaving an argument off -- and a set with a stale identifier would
    otherwise reach a paid run, where the entry reads as one the agent never
    retrieved.
    """
    corpus = load(write_all_shapes_corpus(tmp_path))
    stale = {**SUPPORTED, "expected_entries": [999999]}
    with pytest.raises(QuestionSetError, match="q1 expects \\[999999\\]"):
        load_question_set(write_set(tmp_path, stale), corpus)


# -- 4.11: the unsupported flag, against the corpus ------------------------------


def test_an_unsupported_question_the_corpus_can_answer_is_refused(tmp_path):
    """The most expensive mistake a set can carry.

    The agent answers it correctly and cites, and that is then scored as a
    fabrication -- the evaluation's most-read figure, wrong for the one reason no
    reader would suspect. The corpus and the question are both in hand at this
    moment, so nothing excuses letting it through.
    """
    corpus = load(FIXTURE)
    wrong = Question(
        question_id="q9",
        question="How wide is an E. coli cell?",
        asked_properties=("Cell diameter",),
        asked_organisms=("E. coli",),
        unsupported=True,
    )
    with pytest.raises(QuestionSetError, match="could be answered from"):
        check_against_corpus((wrong,), corpus)


def test_an_unsupported_question_the_corpus_cannot_answer_passes(tmp_path):
    """The other direction, and the one that must not be refused: a set without
    unanswerable questions measures nothing about refusal behaviour."""
    corpus = load(FIXTURE)
    fine = Question(
        question_id="q9",
        question="How many neoblasts does a planarian have?",
        asked_properties=("Number of neoblasts",),
        asked_organisms=("Planarian",),
        unsupported=True,
    )
    _check_shapes_aside(fine, corpus)


def test_a_real_property_asked_of_the_wrong_organism_is_still_unsupported(tmp_path):
    """The conjunction, not either half.

    `Cell volume` is a real property in the fixture and yeast is a real organism,
    but no entry carries both -- yeast appears only with `Cell diameter`. So the
    question is genuinely unanswerable, and refusing it would reject exactly the
    questions the set exists to contain.
    """
    corpus = load(FIXTURE)
    fine = Question(
        question_id="q9",
        question="What is the volume of a yeast cell?",
        asked_properties=("Cell volume",),
        asked_organisms=("Saccharomyces",),
        unsupported=True,
    )
    _check_shapes_aside(fine, corpus)


def _check_shapes_aside(question: Question, corpus) -> None:
    """Run the corpus check on one unsupported question without the shape rule.

    The shape rule needs a set covering all six shapes, which is a different
    concern from the flag being right; asserting them together would make either
    failure look like the other.
    """
    with pytest.raises(QuestionSetError) as raised:
        check_against_corpus((question,), corpus)
    assert "could be answered from" not in str(raised.value)
    assert "shapes" in str(raised.value)


# -- ADR-0530: the admissible list ---------------------------------------------
#
# Its whole job is negative -- it stops a citation being reported as unexpected --
# so every test here is about the list failing to do that quietly. A list read as
# absent, a list overlapping the expected one, a list naming an entry the corpus
# does not hold: each leaves the score looking exactly as it does when the list is
# right.


def test_admissible_entries_are_read_and_kept_apart_from_expected(tmp_path):
    path = write_set(tmp_path, {**SUPPORTED, "admissible_entries": [100011, 100012]})
    (question,) = load_question_set(path, None)
    assert question.admissible_entries == (100011, 100012)
    assert question.expected_entries == (100003, 100004)


def test_an_entry_in_both_lists_is_refused(tmp_path):
    """The lists disagree about what a missing citation means, so an entry in both
    makes the score depend on which is consulted first."""
    path = write_set(tmp_path, {**SUPPORTED, "admissible_entries": [100004]})
    with pytest.raises(QuestionSetError) as raised:
        load_question_set(path, None)
    assert "100004" in str(raised.value)
    assert "expected and" in str(raised.value)


def test_an_unsupported_question_may_not_name_admissible_entries(tmp_path):
    path = write_set(
        tmp_path,
        {
            "question_id": "q1",
            "question": "How many neoblasts does a planarian have?",
            "asked_properties": "Number of neoblasts",
            "asked_organisms": "Planarian",
            "unsupported": True,
            "admissible_entries": [100003],
        },
    )
    with pytest.raises(QuestionSetError) as raised:
        load_question_set(path, None)
    assert "admissible" in str(raised.value)


def test_a_refusal_about_the_admissible_list_names_that_list(tmp_path):
    """Both lists share one reader. A message hard-coded to `expected_entries`
    would send someone to a list that is correct, and the mutant that reintroduces
    it changes nothing a test asserting only the type would see."""
    path = write_set(tmp_path, {**SUPPORTED, "admissible_entries": ["100011"]})
    with pytest.raises(QuestionSetError) as raised:
        load_question_set(path, None)
    assert "admissible_entries" in str(raised.value)
    assert "expected_entries" not in str(raised.value)


def test_an_admissible_entry_the_corpus_does_not_hold_is_refused():
    """Reported apart from a missing expected entry: an expected one gone means
    the question lost support, an admissible one means the exemption lapsed."""
    question = Question(
        question_id="q1",
        question="How big is an E. coli cell?",
        asked_properties=("Cell volume",),
        asked_organisms=("Bacteria Escherichia coli",),
        expected_entries=(1,),
        admissible_entries=(99999,),
    )
    with pytest.raises(QuestionSetError) as raised:
        check_against_corpus((question,), (an_entry(),))
    assert "admissible entry" in str(raised.value)
    assert "99999" in str(raised.value)


def test_a_question_built_directly_also_refuses_unsupported_with_admissible():
    """Two guards stand here and only one was asserted. The reader refuses this
    before `Question` is ever constructed, so disabling the dataclass's own check
    left the suite green -- and the dataclass is the guard that holds for a caller
    building a set programmatically rather than reading a file. Found by seeding."""
    with pytest.raises(QuestionSetError) as raised:
        Question(
            question_id="q1",
            question="How many neoblasts does a planarian have?",
            asked_properties=("Number of neoblasts",),
            asked_organisms=("Planarian",),
            unsupported=True,
            admissible_entries=(100003,),
        )
    assert "admissible" in str(raised.value)


def test_a_false_premise_question_may_rest_on_admissible_entries_alone(tmp_path):
    """The third state the set needs, and neither of the other two fits it.

    "What is the volume of the nucleus of an E. coli cell?" has no expected entry,
    because nothing records the volume of a thing that does not exist. It is not
    unsupported either: the corpus holds the nucleoid, and marking it unsupported
    would score the correct answer -- cite the nucleoid, say the premise does not
    hold -- as a failure to decline.
    """
    false_premise = {
        "question_id": "ecoli-nucleus",
        "question": "What is the volume of the nucleus of an E. coli cell?",
        "asked_properties": "Nuclear",
        "asked_organisms": "Bacteria Escherichia coli",
        "admissible_entries": [100013, 107009],
        "tags": ["false-premise"],
    }
    (question,) = load_question_set(write_set(tmp_path, false_premise), None)
    assert question.expected_entries == ()
    assert question.admissible_entries == (100013, 107009)
    assert not question.unsupported


# -- The tier: what a question demands of the agent -----------------------------


def test_a_question_without_a_tier_is_basic(tmp_path):
    (question,) = load_question_set(write_set(tmp_path, SUPPORTED), None)
    assert question.tier is Tier.BASIC


def test_a_tier_is_read_and_is_case_insensitive(tmp_path):
    (question,) = load_question_set(write_set(tmp_path, {**SUPPORTED, "tier": "Compound"}), None)
    assert question.tier is Tier.COMPOUND


def test_an_unknown_tier_is_refused_by_name_with_the_choices(tmp_path):
    """Unlike a tag, a tier is compared against the same tier in an earlier run.
    Defaulting a mistyped one to `basic` would file it in the bucket whose whole
    purpose is to stay honest about the simple questions."""
    with pytest.raises(QuestionSetError) as raised:
        load_question_set(write_set(tmp_path, {**SUPPORTED, "tier": "compund"}), None)
    assert "compund" in str(raised.value)
    assert "basic" in str(raised.value) and "compound" in str(raised.value)
