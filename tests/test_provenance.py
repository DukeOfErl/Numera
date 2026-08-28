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


def test_the_recorded_time_is_the_sources_mtime_not_the_run_time(tmp_path, sample_html):
    # Named source_modified, so it must BE that. Reporting `now` instead would
    # pass every other test while making two corpora from the same file look
    # like they came from different ones.
    import os
    import time

    src = tmp_path / "dated.html"
    src.write_bytes(sample_html.read_bytes())
    long_ago = time.time() - 90 * 24 * 3600
    os.utime(src, (long_ago, long_ago))

    result = ingest(src, tmp_path / "corpus.jsonl")
    m = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert m["source_modified"] < m["ingested_at"]
    assert m["source_modified"].startswith(
        __import__("datetime")
        .datetime.fromtimestamp(long_ago, tz=__import__("datetime").UTC)
        .isoformat()[:10]
    )


def test_records_written_plus_skipped_equals_rows_read(sample_html, tmp_path):
    result = ingest(sample_html, tmp_path / "corpus.jsonl")
    r = result.report
    assert r.records_written + r.rows_skipped_non_data == r.rows_read
    assert r.rows_accounted_for is True


def test_accounting_that_does_not_add_up_is_reported_as_a_warning():
    from bionumbers_ingest.validation import RunReport

    off = RunReport(rows_read=10, rows_skipped_non_data=1, records_written=8)
    assert off.rows_accounted_for is False
    assert "WARNING" in off.format()


def test_a_limited_run_fingerprints_the_whole_file_anyway(tmp_path, sample_html, monkeypatch):
    # Otherwise two limits that both stop inside the first read block produce the
    # same digest, and two corpora cannot be told apart.
    from bionumbers_ingest.parsing import html_table

    monkeypatch.setattr(html_table, "_CHUNK", 128)
    full = ingest(sample_html, tmp_path / "full.jsonl")
    small = ingest(sample_html, tmp_path / "small.jsonl", limit=1)
    bigger = ingest(sample_html, tmp_path / "bigger.jsonl", limit=4)

    assert small.source_digest == bigger.source_digest == full.source_digest
    for result in (full, small, bigger):
        m = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert m["source_sha256"] == hashlib.sha256(sample_html.read_bytes()).hexdigest()
        assert m["source_size_bytes"] == sample_html.stat().st_size


def test_the_same_source_produces_a_byte_identical_corpus(tmp_path, sample_html):
    # Two people building from the same download must get the same file, or
    # comparing their corpora proves nothing and a difference cannot be
    # attributed. Verified over the real export across three PYTHONHASHSEED
    # values as well, since set iteration order is the usual way this breaks.
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    ingest(sample_html, first)
    ingest(sample_html, second)
    assert first.read_bytes() == second.read_bytes()


def test_two_manifests_of_one_source_differ_only_in_when_they_ran(tmp_path, sample_html):
    a = json.loads(ingest(sample_html, tmp_path / "a.jsonl").manifest_path.read_text())
    b = json.loads(ingest(sample_html, tmp_path / "b.jsonl").manifest_path.read_text())
    differing = {k for k in a if a[k] != b.get(k)}
    assert differing == {"ingested_at"}, (
        f"a manifest field varies between identical runs: {differing - {'ingested_at'}}"
    )


def test_the_report_counts_are_asserted_against_real_values(sample_html, tmp_path):
    """The headline counts must be the counts, not merely present.

    Found by mutation testing: `sum(2 for ...)` on the two predicate counts and on
    `records_with_no_scalar` all survived the suite, because every existing
    assertion used a fixture where those counts are zero — and twice zero is zero.
    These are the numbers the report presents as facts about the corpus.
    """
    result = ingest(sample_html, tmp_path / "corpus.jsonl")
    report = result.report
    records = [
        json.loads(line)
        for line in (tmp_path / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert report.range_fused_count == sum(1 for r in records if r["range_fused"])
    assert report.range_qualified_count == sum(1 for r in records if r["range_qualified"])
    assert report.records_with_no_scalar == sum(
        1 for r in records if r["value"] is None and r["range_low"] is None
    )
    # and they are non-zero here, so a doubled or inverted count would show
    assert report.records_with_no_scalar > 0
    assert report.link_records > 0

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["range_fused_count"] == report.range_fused_count
    assert manifest["range_qualified_count"] == report.range_qualified_count


def test_no_scalar_means_neither_a_value_nor_a_range():
    """`and`, not `or`: a record with a range but no value still has a scalar."""
    from bionumbers_ingest.model import BioNumberRecord
    from bionumbers_ingest.validation import report_for

    records = [
        BioNumberRecord(bnid=1, value=1.5),  # value only
        BioNumberRecord(bnid=2, range_low=1.0, range_high=2.0),  # range only
        BioNumberRecord(bnid=3),  # neither
    ]
    assert report_for(records, rows_read=3, rows_skipped_non_data=0).records_with_no_scalar == 1


@pytest.mark.parametrize("field", ["source_modified", "ingested_at"])
def test_manifest_timestamps_carry_their_timezone(tmp_path, sample_html, field):
    """A naive timestamp is not provenance.

    Two readers in different zones would record incomparable dates for the same
    file, which defeats the point of recording a date at all. Mutation testing
    showed `tz=UTC` could be dropped from either call with nothing failing.
    """
    from datetime import datetime

    result = ingest(sample_html, tmp_path / "corpus.jsonl")
    value = json.loads(result.manifest_path.read_text(encoding="utf-8"))[field]
    assert datetime.fromisoformat(value).tzinfo is not None, f"{field} is naive: {value}"
    assert value.endswith("+00:00"), f"{field} is not UTC: {value}"


def test_the_predicate_counts_count_records_not_something_doubled():
    """Asserted against a record set where both predicates are non-zero.

    The fixture has no fused or qualified record, so `sum(2 for ...)` survived a
    test that compared the count against the corpus: twice zero is zero. A count
    is only asserted by a case where it is not zero.
    """
    from bionumbers_ingest.model import BioNumberRecord
    from bionumbers_ingest.validation import report_for

    records = [
        BioNumberRecord(bnid=1, range_fused=True),
        BioNumberRecord(bnid=2, range_fused=True, range_qualified=True),
        BioNumberRecord(bnid=3, range_qualified=True),
        BioNumberRecord(bnid=4),
    ]
    report = report_for(records, rows_read=4, rows_skipped_non_data=0)
    assert report.range_fused_count == 2
    assert report.range_qualified_count == 2
    assert report.records_written == 4
