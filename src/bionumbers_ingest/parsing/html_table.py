"""Stream rows out of the BioNumbers export (an HTML ``<table>`` saved as ``.xls``).

The first ``<tr>`` holds the column headers; every later ``<tr>`` is a record —
including the trailing padding rows, which this module yields rather than judges.
Deciding what is data belongs to :mod:`bionumbers_ingest.cleaning`.

**Cell content is preserved as raw inner HTML, tags and character references
intact.** That is a contract, not an implementation detail: the export's injected
markup arrives HTML-escaped (``&lt;IMG SRC="/WF_SQL_XSRF.html"&gt;``), and a
reader that unescaped it here would hand cleaning a live tag and destroy the
evidence of which form the source used. Unescaping happens once, in cleaning,
before markup is stripped. See ADR-0230 and `specs/measurement-cleaning`.

Three ways a file can be wrong end the read loudly rather than quietly, because
each of them otherwise produces a short or shifted corpus that loads cleanly:
a truncated table, a row whose cell count disagrees with the header, and — when
the caller supplies the names it expects — a renamed column.
"""

from __future__ import annotations

import codecs
import html as html_module
import re
from collections.abc import Callable, Iterator, Sequence
from html.parser import HTMLParser
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB
_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")


def _header_name(cell: str) -> str:
    """A header cell reduced to the name a caller would write.

    Header cells arrive as raw inner HTML like every other cell — the export pads
    them and marks them bold. Comparing or keying on that raw string means a
    padded header both fails an `expect_headers` check on a perfectly ingestible
    file and, when no check is asked for, silently produces keys nothing looks up,
    so every field comes out empty with nothing flagged.

    Tag stripping here is only to recover a *name*; cell content is still handed
    to cleaning untouched, which is where the markup rules live.
    """
    return _WS_RE.sub(" ", html_module.unescape(_TAG_RE.sub("", cell))).strip()


class _TableParser(HTMLParser):
    """Collects complete ``<tr>`` rows as lists of raw cell strings.

    ``convert_charrefs=False`` plus the ``handle_entityref`` and
    ``handle_charref`` hooks below are what keep character references in their
    source form; the default would silently decode them.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._in_cell = False
        self._buf: list[str] = []
        self._open_tables = 0

    @property
    def incomplete(self) -> bool:
        """A row or a cell was still open when the input ran out.

        Not the whole of truncation: a file cut on a ``</tr>`` boundary leaves
        nothing open, so ``truncated`` below is the check that matters and this
        one only names *where* the cut landed.
        """
        return self._row is not None or self._in_cell

    @property
    def truncated(self) -> bool:
        """The table was opened and the input ran out before it closed.

        A download interrupted between two rows ends on a ``</tr>`` boundary and
        parses perfectly — every row it managed to hold, and no complaint. That is
        the shape this project cannot ship: a corpus that loads cleanly and is
        missing entries nobody can enumerate. So completeness is asserted against
        the closing tag rather than against the parser's open state.

        Counted rather than latched, because a latch cannot tell a closed table
        from a second one opened after it: `<table>…</table><table>…` cut short
        would read as complete. Nesting is handled by the same count.

        ``incomplete`` stays in the disjunction rather than being replaced by it:
        a fragment with no ``<table>`` wrapper at all has no closing tag to miss,
        and an open row is the only evidence of truncation it can offer.
        """
        return self._open_tables > 0 or self.incomplete

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag == "table" and not self._in_cell:
            self._open_tables += 1
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._in_cell = True
            self._buf = []
        elif self._in_cell:
            self._buf.append(self.get_starttag_text() or "")

    def handle_startendtag(self, tag: str, attrs: object) -> None:
        if self._in_cell:
            self._buf.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and not self._in_cell and self._open_tables:
            self._open_tables -= 1
        if tag == "td" and self._in_cell:
            assert self._row is not None
            self._row.append("".join(self._buf))
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif self._in_cell:
            # An end tag inside a cell is content like any other tag. Dropping it
            # joined the words either side of it AND left no tag for cleaning to
            # find, so a contaminated cell raised no markup flag at all.
            self._buf.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._buf.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._in_cell:
            self._buf.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._in_cell:
            self._buf.append(f"&#{name};")


def _iter_raw_rows(
    path: str | Path, on_bytes: Callable[[bytes], None] | None = None
) -> Iterator[list[str]]:
    """Yield every complete ``<tr>`` as a list of raw cells.

    Reads in chunks and drains completed rows after each one, so memory stays
    flat over a 27 MB export rather than growing with it.

    ``on_bytes`` receives each raw chunk before it is decoded, so a caller can
    fingerprint the source in this same pass. Hashing separately would mean a
    second pass over 27 MB and, worse, a second read — which could see a
    different file than the one that was parsed. The file is therefore opened in
    binary and decoded incrementally here rather than by the text layer.

    Raises ``ValueError`` if the input ends mid-row or mid-cell. Without that
    check a truncated download — an interrupted transfer, a half-written file —
    yields every row it managed to parse and stops, producing a short corpus that
    loads cleanly and is missing entries nobody can enumerate.
    """
    parser = _TableParser()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    with open(path, "rb") as fh:
        while True:
            raw = fh.read(_CHUNK)
            if not raw:
                break
            if on_bytes is not None:
                on_bytes(raw)
            # A multi-byte character split across two chunks is held by the
            # decoder until the rest arrives, so this can legitimately be empty.
            chunk = decoder.decode(raw)
            if chunk:
                parser.feed(chunk)
            while parser.rows:
                yield parser.rows.pop(0)
    tail = decoder.decode(b"", final=True)
    if tail:
        parser.feed(tail)
    parser.close()
    while parser.rows:
        yield parser.rows.pop(0)
    if parser.truncated:
        where = "mid-row" if parser.incomplete else "between rows"
        raise ValueError(
            f"the table is never closed and ends {where}: the source file appears "
            f"truncated, so any corpus built from it would be silently short"
        )


def iter_rows(
    path: str | Path,
    limit: int | None = None,
    expect_headers: Sequence[str] | None = None,
    on_bytes: Callable[[bytes], None] | None = None,
) -> Iterator[dict[str, str]]:
    """Yield each row after the header as ``{header: raw_cell}``.

    Stops once ``limit`` rows have been yielded; ``None`` or ``0`` means every row.

    ``expect_headers`` makes the caller's assumption about the schema checkable.
    Cleaning reads fields by name, so a renamed column is invisible to it: rename
    the identifier column and every row fails the is-it-data test, producing an
    empty corpus from a run that reports no error at all; rename any other and
    that field is ``None`` on every record with nothing flagged. Pass the names
    you rely on and a rename becomes a failure instead.

    ``on_bytes`` is handed each raw chunk of the source, for fingerprinting in the
    same pass — see :mod:`bionumbers_ingest.provenance`. Note that a run stopped
    early by ``limit`` has not read the whole file, so any digest taken alongside
    it covers only the part read; the manifest records the limit for that reason.

    Raises ``ValueError`` if a row's cell count does not match the header's. Every
    row of the published export carries exactly 14 cells, so a mismatch is a
    malformed file — and zipping a short row against the headers would drop the
    missing columns without a word, producing a record that looks complete.
    """
    headers: list[str] | None = None
    yielded = 0
    for row in _iter_raw_rows(path, on_bytes=on_bytes):
        if headers is None:
            headers = [_header_name(cell) for cell in row]
            if expect_headers is not None:
                missing = [h for h in expect_headers if h not in headers]
                unexpected = [h for h in headers if h not in expect_headers]
                if missing or unexpected:
                    raise ValueError(
                        f"the export's columns are not the ones expected: "
                        f"missing {missing}, unexpected {unexpected}"
                    )
                # Order is deliberately not checked: cleaning reads fields by
                # name, so a reordered header changes nothing, and failing on it
                # would abort a perfectly ingestible file.
            continue
        if len(row) != len(headers):
            raise ValueError(
                f"row {yielded + 1} has {len(row)} cells, "
                f"but the header declares {len(headers)} columns"
            )
        yield dict(zip(headers, row, strict=True))
        yielded += 1
        if limit and yielded >= limit:
            return
