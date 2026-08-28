"""Write the corpus out: one JSON object per line, and only on a completed run.

JSONL is the only output format. The consumer reads JSONL; a second serialization
path would be a second place the contract could drift, and drift in the direction
that matters is silent — the JSONL keeps satisfying the loader while the other
format has moved on. ADR-0220.

The file appears at its destination only after the last record is written. A
short corpus loads cleanly and is missing entries nobody can enumerate, which is
the failure this project cannot afford.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from bionumbers_ingest.model import BioNumberRecord

#: Suffix of the file written while a run is in progress, beside the destination
#: so the rename into place is atomic rather than a copy across filesystems.
PARTIAL_SUFFIX = ".partial"


def write_corpus(records: Iterable[BioNumberRecord], path: str | Path) -> int:
    """Write ``records`` as JSONL to ``path`` and return how many were written.

    Writes to ``<path>.partial`` and renames it into place after the last record.
    A run that raises partway leaves the previous corpus untouched, or no file at
    all — never a truncated one. The partial file is removed on the way out.

    Scalars that are absent are emitted as JSON ``null``, never as ``""``: the
    consumer coerces ``""`` to ``None`` for scalars, but ``""`` is not ``None``,
    so an empty string satisfies its has-a-value branch and blanks out every
    range-only entry. ``keywords`` is an array, never a joined string — the
    consumer's ``tuple()`` over a string would yield one entry per character.
    Both come free from ``model_dump_json``; both are pinned by the contract tests.
    """
    path = Path(path)
    partial = path.with_name(path.name + PARTIAL_SUFFIX)
    path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    try:
        with open(partial, "w", encoding="utf-8") as fh:
            for record in records:
                fh.write(record.model_dump_json())
                fh.write("\n")
                written += 1
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(partial, path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return written
