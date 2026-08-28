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
import secrets
from collections.abc import Iterable
from pathlib import Path

from bionumbers_ingest.model import BioNumberRecord

#: Suffix of the file written while a run is in progress, beside the destination
#: so the rename into place is atomic rather than a copy across filesystems.
#: Last, so that a `*.partial` ignore rule covers the unique names below.
PARTIAL_SUFFIX = ".partial"


def partial_path_for(path: Path) -> Path:
    """A scratch path for ``path``, unique to this write.

    **Two builds of the same corpus must not share a scratch file.** The README
    tells a reader to start either driver, so a terminal session and a Streamlit
    server both finding no corpus is a documented arrangement rather than an
    exotic one — and both would then truncate and write one fixed `.partial`.
    Interleaved at buffer boundaries that yields whole-but-duplicated JSONL lines,
    which the consumer's loader accepts without complaint.

    A silently wrong corpus, and — because a corpus that exists is never rebuilt —
    a permanent one. The never-rebuild rule is right and is what makes this worth
    more than its odds: it turns a transient race into an artefact nobody
    reconsiders.

    Uniqueness rather than a lock, because both writers then finish and the last
    rename wins, which costs a duplicated minute and nothing else. A lock would
    make the second launch fail instead, and would leave a stale file blocking
    every later build after a kill. The same export produces a byte-identical
    corpus, so the two racers are writing the same bytes anyway.
    """
    unique = f"{os.getpid()}-{secrets.token_hex(4)}"
    return path.with_name(f"{path.name}.{unique}{PARTIAL_SUFFIX}")


def write_corpus(
    records: Iterable[BioNumberRecord], path: str | Path, partial: Path | None = None
) -> int:
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
    # The caller may hand in the scratch path so the git guard can be asked about
    # the file that will actually exist, rather than about a representative name.
    partial = partial or partial_path_for(path)
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
