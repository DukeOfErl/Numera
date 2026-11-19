"""On-disk cache for retrieved documents, keyed by identifier and version.

The benchmark is re-run often during development. Re-fetching the same few hundred documents each
time is slow and impolite to a free service.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


class DocumentCache:
    """Stores document text under a filename derived from its identifier and version."""

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    def get(self, identifier: str, version: str, suffix: str = ".xml") -> str | None:
        path = self._path(identifier, version, suffix)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def put(self, identifier: str, version: str, content: str, suffix: str = ".xml") -> None:
        path = self._path(identifier, version, suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename: an interrupted run must not leave a half-written document behind that
        # a later run would read back as complete.
        temporary = path.with_name(path.name + ".partial")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def _path(self, identifier: str, version: str, suffix: str) -> Path:
        key = f"{identifier}@{version}"
        readable = _UNSAFE.sub("_", key)[:80]
        # The digest keeps distinct keys apart after the unsafe-character substitution and the
        # length cap have collapsed them.
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        return self.directory / f"{readable}.{digest}{suffix}"
