import json

import pytest

from bionumbers_ingest.cleaning import clean_row, is_data_row
from bionumbers_ingest.io import PARTIAL_SUFFIX, write_corpus
from bionumbers_ingest.model import BioNumberRecord
from bionumbers_ingest.parsing import iter_rows


def _records(sample_html):
    return [clean_row(raw) for raw in iter_rows(sample_html) if is_data_row(raw)]


def test_one_json_object_per_line(tmp_path, sample_html):
    out = tmp_path / "corpus.jsonl"
    n = write_corpus(_records(sample_html), out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert n == len(lines) == 6
    for line in lines:
        assert isinstance(json.loads(line), dict)


def test_the_file_ends_with_a_newline(tmp_path, sample_html):
    # a reader that appends, or a shell that cats two corpora, must not join
    # the last record of one to the first of the next
    out = tmp_path / "corpus.jsonl"
    write_corpus(_records(sample_html), out)
    assert out.read_text(encoding="utf-8").endswith("\n")


def test_absent_scalars_are_null_and_never_empty_strings(tmp_path):
    out = tmp_path / "corpus.jsonl"
    write_corpus([BioNumberRecord(entry_id=1)], out)
    obj = json.loads(out.read_text(encoding="utf-8"))
    for key in ("value", "range_low", "range_high"):
        assert obj[key] is None, f"{key} must be null"
    assert '""' not in out.read_text(encoding="utf-8")


def test_keywords_is_an_array_and_entry_id_is_a_number(tmp_path):
    out = tmp_path / "corpus.jsonl"
    write_corpus([BioNumberRecord(entry_id=900001, keywords=["a", "b"])], out)
    obj = json.loads(out.read_text(encoding="utf-8"))
    assert obj["keywords"] == ["a", "b"]
    assert isinstance(obj["entry_id"], int)


def test_the_predicate_and_the_flags_are_on_every_line(tmp_path, sample_html):
    out = tmp_path / "corpus.jsonl"
    write_corpus(_records(sample_html), out)
    for line in out.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        assert "parse_flags" in obj and isinstance(obj["parse_flags"], list)
        assert "range_fused" in obj and isinstance(obj["range_fused"], bool)


def test_a_run_that_raises_partway_leaves_no_file(tmp_path):
    out = tmp_path / "corpus.jsonl"

    def records():
        yield BioNumberRecord(entry_id=1)
        yield BioNumberRecord(entry_id=2)
        raise RuntimeError("source went away")

    with pytest.raises(RuntimeError, match="source went away"):
        write_corpus(records(), out)
    assert not out.exists(), "a partial corpus was left at the destination"
    assert not list(tmp_path.glob("*" + PARTIAL_SUFFIX)), "the partial file was left behind"


def test_a_failed_run_leaves_a_previous_corpus_untouched(tmp_path):
    out = tmp_path / "corpus.jsonl"
    write_corpus([BioNumberRecord(entry_id=1)], out)
    before = out.read_text(encoding="utf-8")

    def records():
        yield BioNumberRecord(entry_id=2)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        write_corpus(records(), out)
    assert out.read_text(encoding="utf-8") == before


def test_the_destination_directory_is_created(tmp_path):
    out = tmp_path / "nested" / "deeper" / "corpus.jsonl"
    write_corpus([BioNumberRecord(entry_id=1)], out)
    assert out.exists()


def test_two_writes_of_one_corpus_do_not_share_a_scratch_file(tmp_path):
    """Two builds of the same corpus must not truncate one fixed `.partial`.

    The README tells a reader to start either driver, so a terminal session and a
    Streamlit server both finding no corpus is a documented arrangement. Sharing
    the scratch file, interleaved at buffer boundaries, yields whole-but-duplicated
    JSONL lines that the consumer's loader accepts without complaint — a corpus
    silently wrong, and permanent, because one that exists is never rebuilt.
    """
    from bionumbers_ingest.io import partial_path_for

    target = tmp_path / "bionumbers.jsonl"
    assert partial_path_for(target) != partial_path_for(target)


def test_a_scratch_file_still_ends_in_the_suffix_the_ignore_rules_name(tmp_path):
    """`*.partial` has to keep covering it, or a kill leaves a committable file."""
    from bionumbers_ingest.io import PARTIAL_SUFFIX, partial_path_for

    assert partial_path_for(tmp_path / "bionumbers.jsonl").name.endswith(PARTIAL_SUFFIX)


def test_the_writer_uses_the_scratch_path_it_is_handed(tmp_path):
    """The guard is asked about that path, so the writer must not invent another."""
    from bionumbers_ingest.io import write_corpus

    seen = tmp_path / "chosen.partial"
    target = tmp_path / "corpus.jsonl"
    write_corpus([], target, partial=seen)
    assert target.is_file() and not seen.exists()
