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

from collections.abc import Iterator, Sequence
from html.parser import HTMLParser
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB


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

    @property
    def incomplete(self) -> bool:
        """A row or a cell was still open when the input ran out."""
        return self._row is not None or self._in_cell

    def handle_starttag(self, tag: str, attrs: object) -> None:
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
        if tag == "td" and self._in_cell:
            assert self._row is not None
            self._row.append("".join(self._buf))
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._buf.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._in_cell:
            self._buf.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._in_cell:
            self._buf.append(f"&#{name};")


def _iter_raw_rows(path: str | Path) -> Iterator[list[str]]:
    """Yield every complete ``<tr>`` as a list of raw cells.

    Reads in chunks and drains completed rows after each one, so memory stays
    flat over a 27 MB export rather than growing with it.

    Raises ``ValueError`` if the input ends mid-row or mid-cell. Without that
    check a truncated download — an interrupted transfer, a half-written file —
    yields every row it managed to parse and stops, producing a short corpus that
    loads cleanly and is missing entries nobody can enumerate.
    """
    parser = _TableParser()
    with open(path, encoding="utf-8", errors="replace") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            parser.feed(chunk)
            while parser.rows:
                yield parser.rows.pop(0)
    parser.close()
    while parser.rows:
        yield parser.rows.pop(0)
    if parser.incomplete:
        raise ValueError(
            "the table ends mid-row: the source file appears truncated, "
            "so any corpus built from it would be silently short"
        )


def iter_rows(
    path: str | Path,
    limit: int | None = None,
    expect_headers: Sequence[str] | None = None,
) -> Iterator[dict[str, str]]:
    """Yield each row after the header as ``{header: raw_cell}``.

    Stops once ``limit`` rows have been yielded; ``None`` or ``0`` means every row.

    ``expect_headers`` makes the caller's assumption about the schema checkable.
    Cleaning reads fields by name, so a renamed column is invisible to it: rename
    the identifier column and every row fails the is-it-data test, producing an
    empty corpus from a run that reports no error at all; rename any other and
    that field is ``None`` on every record with nothing flagged. Pass the names
    you rely on and a rename becomes a failure instead.

    Raises ``ValueError`` if a row's cell count does not match the header's. Every
    row of the published export carries exactly 14 cells, so a mismatch is a
    malformed file — and zipping a short row against the headers would drop the
    missing columns without a word, producing a record that looks complete.
    """
    headers: list[str] | None = None
    yielded = 0
    for row in _iter_raw_rows(path):
        if headers is None:
            headers = row
            if expect_headers is not None and list(headers) != list(expect_headers):
                missing = [h for h in expect_headers if h not in headers]
                unexpected = [h for h in headers if h not in expect_headers]
                raise ValueError(
                    f"the export's columns are not the ones expected: "
                    f"missing {missing}, unexpected {unexpected}"
                )
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
