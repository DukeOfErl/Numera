"""The evaluation command, which so far only checks a question set.

Every refusal here is one the operation already makes -- the command's job is to
turn it into a sentence and a non-zero exit rather than a traceback, which is what
an unattended run needs.
"""

from __future__ import annotations

import json

import pytest

from scinumbers_ask.eval_cli import main

FIXTURE_CORPUS = "tests/fixtures/corpus_sample.jsonl"

SUPPORTED = {
    "question_id": "q1",
    "question": "How long is an E. coli cell?",
    "asked_property": "Cell length",
    "asked_organism": "Bacteria Escherichia coli",
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
        "asked_property": "Number of neoblasts",
        "asked_organism": "Planarian",
        "unsupported": True,
    }
    main(["check", write_set(tmp_path, SUPPORTED, followup, unsupported)])
    assert "3 questions, 1 unsupported, 1 follow-ups." in capsys.readouterr().out


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
