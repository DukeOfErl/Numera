"""Identify the file a corpus came from, and when.

The export carries **no temporal information whatsoever**. None of its 14 columns
is a date, and every date-shaped string in it belongs to a citation. So once a
download's file time is lost, two corpus files cannot be told apart and neither
can be dated — and a corpus that cannot be dated cannot be reproduced, corrected
or retired. Every run therefore records what it read and when. ADR-0240.

The source's modification time is named as such, not as a fetch time: it is the
only available proxy for when the file was obtained, and calling it a fetch time
would assert something the file cannot support.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

#: Characters of the digest carried on each record. Enough to tie a line to its
#: manifest without putting 64 characters on all 14,294 of them.
STAMP_LENGTH = 12


class SourceDigest:
    """Accumulates a SHA-256 and a byte count as the source is read.

    Fed from the reader's own byte chunks, so the 27 MB file is hashed in the same
    pass that parses it. Hashing separately would mean a second pass, and — worse —
    a second read, which could see a different file.
    """

    def __init__(self) -> None:
        self._hash = hashlib.sha256()
        self.size_bytes = 0

    def update(self, chunk: bytes) -> None:
        self._hash.update(chunk)
        self.size_bytes += len(chunk)

    def complete_from(self, path: str | Path) -> None:
        """Hash whatever of ``path`` has not been fed in yet.

        A run stopped early by ``--limit`` never reaches the end of the file, so
        without this the recorded digest and size describe only the part read —
        under names that assert whole-file facts. Worse, two different limits
        that both stop inside the first chunk produce the *same* digest, so two
        corpora could not be told apart, which is the failure this module exists
        to prevent. Reading the remaining bytes is cheap; being wrong is not.
        """
        total = os.path.getsize(path)
        if self.size_bytes >= total:
            return
        with open(path, "rb") as fh:
            fh.seek(self.size_bytes)
            while chunk := fh.read(1 << 20):
                self.update(chunk)

    @property
    def hexdigest(self) -> str:
        return self._hash.hexdigest()

    @property
    def stamp(self) -> str:
        """The short form carried on each record."""
        return self._hash.hexdigest()[:STAMP_LENGTH]


@dataclass
class Manifest:
    """What one run read, what it produced, and what it could not interpret."""

    source_path: str
    source_sha256: str
    source_size_bytes: int
    source_modified: str
    ingested_at: str
    ingester_version: str
    rows_read: int
    records_written: int
    rows_skipped_non_data: int
    duplicate_bnids: list[int]
    flag_counts: dict[str, int]
    range_fused_count: int
    range_qualified_count: int = 0
    row_limit: int | None = None
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def stamp(self) -> str:
        return self.source_sha256[:STAMP_LENGTH]

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, sort_keys=True) + "\n"


def source_modified_at(path: str | Path) -> str:
    """The source file's modification time, in UTC, ISO 8601.

    Named for what it is. It is not when the file was fetched — nothing records
    that — but it is the only thing that comes close, and it is at least stable
    across copies made with the time preserved.
    """
    return datetime.fromtimestamp(os.path.getmtime(path), tz=UTC).isoformat()


def ingested_at() -> str:
    return datetime.now(tz=UTC).isoformat()


def manifest_path_for(corpus_path: str | Path) -> Path:
    """The manifest sits beside its corpus, named after it."""
    corpus_path = Path(corpus_path)
    return corpus_path.with_name(corpus_path.name + ".manifest.json")


def write_manifest(manifest: Manifest, corpus_path: str | Path) -> Path:
    """Write the manifest beside the corpus, corpus first.

    Called only after the corpus is in place, so a corpus with no manifest is a
    run that did not finish — and never the reverse, which would leave a manifest
    describing a corpus that does not exist.
    """
    path = manifest_path_for(corpus_path)
    partial = path.with_name(path.name + ".partial")
    try:
        partial.write_text(manifest.to_json(), encoding="utf-8")
        os.replace(partial, path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return path
