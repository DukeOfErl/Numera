"""The evaluation command, which so far only checks a question set.

Every refusal here is one the operation already makes -- the command's job is to
turn it into a sentence and a non-zero exit rather than a traceback, which is what
an unattended run needs.
"""

from __future__ import annotations

import json

import pytest
from conftest import write_all_shapes_corpus

from scinumbers_ask.eval_cli import main

FIXTURE_CORPUS = "tests/fixtures/corpus_sample.jsonl"

SUPPORTED = {
    "question_id": "q1",
    "question": "How long is an E. coli cell?",
    "asked_properties": "Cell length",
    "asked_organisms": "Bacteria Escherichia coli",
    "expected_entries": [100001],
}


@pytest.fixture(autouse=True)
def _no_corpus_from_the_environment(monkeypatch):
    """A developer with SCINUMBERS_CORPUS set would otherwise get a different run.

    `--corpus` defaults to that variable, so without this the structure-only tests
    below would silently exercise the corpus path against whatever corpus is on
    that machine.
    """
    monkeypatch.delenv("SCINUMBERS_CORPUS", raising=False)


def write_set(tmp_path, *records):
    path = tmp_path / "questions.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return str(path)


def test_a_valid_set_is_reported_with_its_composition(tmp_path, capsys):
    followup = {**SUPPORTED, "question_id": "q1b", "follows": "q1"}
    unsupported = {
        "question_id": "q2",
        "question": "How many neoblasts does a planarian have?",
        "asked_properties": "Number of neoblasts",
        "asked_organisms": "Planarian",
        "unsupported": True,
    }
    main(["check", write_set(tmp_path, SUPPORTED, followup, unsupported)])
    assert "3 questions, 1 unsupported, 1 follow-up." in capsys.readouterr().out


def test_the_composition_line_counts_more_than_one_follow_up(tmp_path, capsys):
    """Only here to hold the plural: "1 follow-ups" was in the first output."""
    followups = [
        {**SUPPORTED, "question_id": "q1b", "follows": "q1"},
        {**SUPPORTED, "question_id": "q1c", "follows": "q1"},
    ]
    main(["check", write_set(tmp_path, SUPPORTED, *followups)])
    assert "2 follow-ups." in capsys.readouterr().out


def test_a_check_without_a_corpus_says_what_it_did_not_check(tmp_path, capsys):
    """The failure this prevents: a structural pass read as a full pass.

    Without the sentence, a set naming an identifier no corpus holds passes this
    command and the absence surfaces only as an entry the agent never retrieved,
    a hundred questions into a paid run.
    """
    main(["check", write_set(tmp_path, SUPPORTED)])
    out = capsys.readouterr().out
    assert "Structure only" in out and "were not checked" in out


def test_an_unusable_set_exits_non_zero_with_the_reason(tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        main(["check", write_set(tmp_path, {**SUPPORTED, "expected_entries": []})])
    assert "scinumbers-eval:" in str(exit_info.value)
    assert "names no expected entries" in str(exit_info.value)


def test_no_question_set_file_exits_rather_than_raising(tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        main(["check", str(tmp_path / "absent.jsonl")])
    assert "No question set file" in str(exit_info.value)


def test_an_identifier_the_corpus_does_not_hold_is_refused_at_the_command(tmp_path):
    """The corpus path reaching the command, not only the loader."""
    stale = {**SUPPORTED, "expected_entries": [999999]}
    with pytest.raises(SystemExit) as exit_info:
        main(["check", write_set(tmp_path, stale), "--corpus", FIXTURE_CORPUS])
    assert "q1 expects [999999]" in str(exit_info.value)


def test_a_missing_corpus_file_explains_itself(tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        main(["check", write_set(tmp_path, SUPPORTED), "--corpus", str(tmp_path / "none.jsonl")])
    assert "No corpus file at" in str(exit_info.value)


def test_a_retired_variable_is_refused_before_anything_is_read(monkeypatch):
    """It would otherwise mean no corpus, and the check would quietly do less.

    Refused before the parser exists, because `--corpus` reads the environment as
    its default and argparse evaluates that when the argument is declared.
    """
    monkeypatch.setenv("BIONUMBERS_ASK_CORPUS", "/somewhere/corpus.jsonl")
    with pytest.raises(SystemExit) as exit_info:
        main(["check", "does-not-matter.jsonl"])
    assert "SCINUMBERS_CORPUS" in str(exit_info.value)


def test_a_set_that_satisfies_the_corpus_is_reported_as_checked(tmp_path, capsys):
    """The passing path through the command, which no test executed before.

    Both corpus tests here refused, so the line saying the set *is* checked ran in
    no test at all -- the shape of gap the project's coverage note calls a path
    hidden behind a double.
    """
    corpus = write_all_shapes_corpus(tmp_path)
    questions = [
        {
            "question_id": f"q{identifier}",
            "question": "How big is an E. coli cell?",
            "asked_properties": "Cell volume",
            "asked_organisms": "Bacteria Escherichia coli",
            "expected_entries": [identifier],
        }
        for identifier in range(1, 7)
    ]
    main(["check", write_set(tmp_path, *questions), "--corpus", corpus])
    out = capsys.readouterr().out
    assert "6 questions, 0 unsupported, 0 follow-ups." in out
    assert "every entry shape is exercised" in out
    assert "Structure only" not in out


def test_a_shape_no_question_exercises_is_refused_at_the_command(tmp_path):
    """The other direction of the same check, through the command."""
    corpus = write_all_shapes_corpus(tmp_path)
    only_complete = {**SUPPORTED, "expected_entries": [1]}
    with pytest.raises(SystemExit) as exit_info:
        main(["check", write_set(tmp_path, only_complete), "--corpus", corpus])
    assert "No question's expected entries carry these shapes" in str(exit_info.value)


def test_the_corpus_is_resolved_the_way_the_ask_command_resolves_it(tmp_path, monkeypatch, capsys):
    """A configured export used to be read as a corpus and reported as corrupt.

    `scinumbers-ask` goes through `autobuild.corpus_path`, which resolves an `.xls`
    to the corpus beside it; this command called `load` on the configured path, so
    the same environment gave one command a working corpus and the other a JSON
    parse error over HTML. Asserted by watching the resolution, because building a
    real corpus from an export is not something a unit test should do.
    """
    seen = []

    def resolve(configured, announce):
        seen.append(configured)
        announce("resolving")
        return write_all_shapes_corpus(tmp_path)

    monkeypatch.setattr("scinumbers_ask.autobuild.corpus_path", resolve)
    questions = [
        {**SUPPORTED, "question_id": f"q{i}", "expected_entries": [i]} for i in range(1, 7)
    ]
    main(["check", write_set(tmp_path, *questions), "--corpus", "/somewhere/BioNumbers.xls"])
    assert seen == ["/somewhere/BioNumbers.xls"]
    # On stderr, because stdout carries what a person or a script reads.
    captured = capsys.readouterr()
    assert "resolving" in captured.err and "resolving" not in captured.out


def test_a_run_without_a_corpus_is_refused_before_a_model_is_built(tmp_path):
    """`check` can work without a corpus and `run` cannot, so the refusal is on the
    subcommand rather than on the loader -- and it comes before the agent is
    constructed, which is what stops "no corpus" arriving as a missing API key."""
    with pytest.raises(SystemExit) as exit_info:
        main(["run", write_set(tmp_path, SUPPORTED), "--results", str(tmp_path / "r.jsonl")])
    assert "A run needs a corpus" in str(exit_info.value)


def test_both_subcommands_are_offered(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "check" in out and "run" in out
