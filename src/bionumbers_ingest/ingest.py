"""The pipeline: source file in, corpus and manifest and report out.

Read as a pipeline whose two ends are the only parts that know a file format —
the HTML reader in, the JSONL writer out. Nothing between them knows either.

**Records are collected before being written, and that is a deliberate cost.**
Each record carries a short digest of the source as its join key to the manifest,
and a digest of the whole file is not known until the last byte of it has been
read. The alternatives were worse: hashing in a separate pass means reading the
27 MB file twice and risking a digest that describes a different file than the one
parsed, and stamping records with anything less than a whole-file digest makes the
join key meaningless. So the read stays streaming — the reader's contract, which
keeps its memory flat — and the records are held instead, bounded by the size of
the corpus rather than growing with the input.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bionumbers_ingest import provenance
from bionumbers_ingest.cleaning import clean_row, is_data_row
from bionumbers_ingest.io import write_corpus
from bionumbers_ingest.model import EXPECTED_HEADERS, BioNumberRecord
from bionumbers_ingest.parsing import iter_rows
from bionumbers_ingest.validation import RunReport, report_for

VERSION = "0.1.0"


@dataclass
class IngestResult:
    corpus_path: Path
    manifest_path: Path
    report: RunReport
    source_digest: str
    """Short form, as stamped on every record."""


def build_records(
    source: str | Path,
    limit: int | None = None,
) -> tuple[list[BioNumberRecord], int, int, provenance.SourceDigest]:
    """Clean every data row of ``source`` and fingerprint the file as it is read.

    Returns the records, the number of rows read, the number skipped as non-data,
    and the accumulated digest. The digest is fed from the reader's own byte
    chunks, so the file is hashed in the pass that parses it rather than in a
    second read.
    """
    digest = provenance.SourceDigest()
    records: list[BioNumberRecord] = []
    rows_read = 0
    skipped = 0
    for raw in iter_rows(
        source, limit=limit, expect_headers=EXPECTED_HEADERS, on_bytes=digest.update
    ):
        rows_read += 1
        if not is_data_row(raw):
            skipped += 1
            continue
        records.append(clean_row(raw))
    return records, rows_read, skipped, digest


def ingest(
    source: str | Path,
    corpus_path: str | Path,
    limit: int | None = None,
) -> IngestResult:
    """Turn the export into a corpus, a manifest and a report.

    The corpus appears at ``corpus_path`` only after the last record is written,
    and the manifest only after the corpus — so a corpus with no manifest is a run
    that did not finish, and never the reverse.
    """
    source = Path(source)
    corpus_path = Path(corpus_path)

    records, rows_read, skipped, digest = build_records(source, limit=limit)
    # A limited run stops before the end of the file, so finish the fingerprint
    # over the rest of it: the manifest names these as whole-file facts.
    digest.complete_from(source)
    stamp = digest.stamp
    for record in records:
        record.source_digest = stamp

    report = report_for(records, rows_read, skipped, row_limit=limit)
    write_corpus(records, corpus_path)

    manifest = provenance.Manifest(
        source_path=str(source),
        source_sha256=digest.hexdigest,
        source_size_bytes=digest.size_bytes,
        source_modified=provenance.source_modified_at(source),
        ingested_at=provenance.ingested_at(),
        ingester_version=VERSION,
        rows_read=report.rows_read,
        records_written=report.records_written,
        rows_skipped_non_data=report.rows_skipped_non_data,
        duplicate_bnids=report.duplicate_bnids,
        flag_counts=report.flag_counts,
        range_fused_count=report.range_fused_count,
        range_qualified_count=report.range_qualified_count,
        row_limit=limit,
        notes={
            "source_modified": (
                "the source file's modification time, which is the only available "
                "proxy for when it was fetched -- the export carries no date of its own"
            ),
        },
    )
    manifest_path = provenance.write_manifest(manifest, corpus_path)
    return IngestResult(corpus_path, manifest_path, report, stamp)
