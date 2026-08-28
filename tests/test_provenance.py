import hashlib
import json

import pytest

from bionumbers_ingest import provenance
from bionumbers_ingest.ingest import build_records, ingest
from bionumbers_ingest.parsing import iter_rows
from bionumbers_ingest.provenance import STAMP_LENGTH, SourceDigest


def test_the_digest_is_taken_from_the_bytes_the_reader_parsed(sample_html):
    # Same file, same pass: hashing separately would mean a second read, which
    # could see a different file than the one that was parsed.
    digest = SourceDigest()
    list(iter_rows(sample_html, on_bytes=digest.update))
    assert digest.hexdigest == hashlib.sha256(sample_html.read_bytes()).hexdigest()
    assert digest.size_bytes == sample_html.stat().st_size


def test_the_stamp_is_the_leading_characters_of_the_digest(sample_html):
    digest = SourceDigest()
    list(iter_rows(sample_html, on_bytes=digest.update))
    assert digest.stamp == digest.hexdigest[:STAMP_LENGTH]
    assert len(digest.stamp) == 12


def test_a_multibyte_character_split_across_chunks_still_decodes(tmp_path, monkeypatch):
    # The reader decodes incrementally now that it reads bytes. A μ landing on a
    # chunk boundary must not become two replacement characters.
    from bionumbers_ingest.parsing import html_table

    src = tmp_path / "mu.html"
    src.write_text(
        "<table><tr><td>bion_id</td><td>Units</td></tr>"
        "<tr><td>1</td><td>" + "μ" * 40 + "m</td></tr></table>",
        encoding="utf-8",
    )
    monkeypatch.setattr(html_table, "_CHUNK", 7)  # forces splits mid-character
    rows = list(iter_rows(src))
    assert rows[0]["Units"] == "μ" * 40 + "m"
    assert "�" not in rows[0]["Units"]


def test_every_record_carries_the_same_stamp(tmp_path, sample_html):
    out = tmp_path / "corpus.jsonl"
    result = ingest(sample_html, out)
    stamps = {json.loads(line)["source_digest"] for line in out.read_text().splitlines()}
    assert stamps == {result.source_digest}
    assert len(result.source_digest) == 12


def test_two_sources_give_two_different_stamps(tmp_path, sample_html):
    other = tmp_path / "other.html"
    other.write_text(
        sample_html.read_text(encoding="utf-8").replace("900001", "900099"),
        encoding="utf-8",
    )
    a = ingest(sample_html, tmp_path / "a.jsonl")
    b = ingest(other, tmp_path / "b.jsonl")
    assert a.source_digest != b.source_digest


def test_the_manifest_sits_beside_the_corpus_and_records_the_run(tmp_path, sample_html):
    out = tmp_path / "corpus.jsonl"
    result = ingest(sample_html, out)
    assert result.manifest_path == tmp_path / "corpus.jsonl.manifest.json"
    m = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert m["source_sha256"] == hashlib.sha256(sample_html.read_bytes()).hexdigest()
    assert m["source_size_bytes"] == sample_html.stat().st_size
    assert m["records_written"] == 6
    assert m["rows_read"] == 7
    assert m["rows_skipped_non_data"] == 1
    assert m["duplicate_bnids"] == []
    assert m["row_limit"] is None
    assert m["ingester_version"]
    assert m["source_sha256"].startswith(result.source_digest)
    # Named for what it is, not as a fetch time the file cannot support.
    assert "source_modified" in m
    assert not any("fetch" in key for key in m), (
        f"a key claims to record a fetch time the export cannot support: {sorted(m)}"
    )


def test_a_records_stamp_matches_its_own_manifest(tmp_path, sample_html):
    out = tmp_path / "corpus.jsonl"
    result = ingest(sample_html, out)
    m = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    for line in out.read_text(encoding="utf-8").splitlines():
        assert m["source_sha256"].startswith(json.loads(line)["source_digest"])


def test_a_limited_run_says_so_in_its_manifest(tmp_path, sample_html):
    result = ingest(sample_html, tmp_path / "corpus.jsonl", limit=3)
    m = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert m["row_limit"] == 3
    assert m["rows_read"] == 3
    assert "ROW LIMIT APPLIED" in result.report.format()


def test_the_manifest_is_written_after_the_corpus(tmp_path, sample_html):
    # A corpus with no manifest is an unfinished run; a manifest describing a
    # corpus that does not exist would be worse, so the order is fixed.
    out = tmp_path / "corpus.jsonl"
    result = ingest(sample_html, out)
    assert out.stat().st_mtime_ns <= result.manifest_path.stat().st_mtime_ns


def test_no_partial_files_are_left_behind(tmp_path, sample_html):
    ingest(sample_html, tmp_path / "corpus.jsonl")
    assert not list(tmp_path.glob("*.partial"))


def test_the_digest_covers_only_what_a_limited_run_read(sample_html):
    whole = SourceDigest()
    list(iter_rows(sample_html, on_bytes=whole.update))
    part = SourceDigest()
    list(iter_rows(sample_html, limit=1, on_bytes=part.update))
    # Documented consequence rather than a defect: a sampled run has not read the
    # whole file, which is why the manifest records the limit.
    assert part.size_bytes <= whole.size_bytes


def test_the_manifest_path_helper_matches_what_a_run_writes(tmp_path, sample_html):
    out = tmp_path / "corpus.jsonl"
    assert provenance.manifest_path_for(out) == ingest(sample_html, out).manifest_path


def test_build_records_reports_rows_read_and_skipped(sample_html):
    records, rows_read, skipped, digest = build_records(sample_html)
    assert len(records) == 6
    assert rows_read == 7
    assert skipped == 1
    assert digest.size_bytes > 0


@pytest.mark.parametrize("limit,expected", [(1, 1), (3, 3), (99, 6)])
def test_a_limit_bounds_the_records(sample_html, limit, expected):
    records, _, _, _ = build_records(sample_html, limit=limit)
    assert len(records) == min(expected, 6)


def test_the_manifest_promises_nothing_it_does_not_record(tmp_path, sample_html):
    # A declared-but-never-populated field is a promise unkept: a reader sees the
    # key, expects the fact, and gets null.
    result = ingest(sample_html, tmp_path / "corpus.jsonl")
    m = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    unpopulated = [k for k, v in m.items() if v is None and k != "row_limit"]
    assert unpopulated == [], f"manifest keys declared but never filled: {unpopulated}"
