"""The JATS reader: a Europe PMC full-text XML becomes passages with ids (design D3).

A passage is the unit everywhere downstream. The model is asked to quote *and* to name the id it
quoted from; `quotes.verify` checks the named passage first and the whole paper second; the review
page shows a cell as its headers plus the cell rather than as the whole table. So the shapes here
are chosen for those three readers, and the reader itself decides nothing about the science.

Two things are deliberate rather than convenient. A `<xref ref-type="bibr">` becomes a `[ref N]`
token in the text instead of being stripped, because that marker is the decisive cue between a
value the paper measured and one it cites (D2), and `quotes.fold` removes the token again before
comparing, so a model that quotes with or without it is verified either way. And a table cell
carries its row and column headers, because the scientist report's clearest finding is that the
cell is the authoritative statement and the prose paraphrases it -- a cell without its headers is
a number with no property and no condition.

Ids are positional in document order and nothing else, so two reads of the same XML produce the
same ids and the same `render_for_model` string. Prompt caching depends on that string being
byte-identical across calls, which is also why nothing here consults the clock or a random source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

from bionumbers.records import Location, TableCell, TableView

_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_WHITESPACE = re.compile(r"\s+")

#: How a `<sup>` reaches the text. Flattened with no marker, `2.5 x 10<sup>8</sup>` read
#: `2.5 x 108`: a correct quote failed the checker and a wrong one could pass it (code review
#: of 2026-09-21, finding 3). Digits and signs become the Unicode superscript characters, so
#: the page shows what the paper printed; anything else -- a footnote letter, a word -- is
#: marked with a caret, `^a`, which is our notation but an honest one. `quotes.fold` reduces
#: both forms to the caret form before comparing. A `<sub>` still flattens: `CO<sub>2</sub>`
#: as `CO2` changes no number's magnitude, and it is what every model writes.
#: Code points rather than the characters, so no editor's normalisation can touch the table.
_SUPERSCRIPT = str.maketrans(
    "0123456789+-=()ni",
    "".join(
        chr(code)
        for code in (
            0x2070,
            0x00B9,
            0x00B2,
            0x00B3,
            0x2074,
            0x2075,
            0x2076,
            0x2077,
            0x2078,
            0x2079,
            0x207A,
            0x207B,
            0x207C,
            0x207D,
            0x207E,
            0x207F,
            0x2071,
        )
    ),
)
_SUPERSCRIPTABLE = re.compile(r"\A[0-9+\-=()ni]+\Z")

#: A section counts as methods when its title, casefolded, holds one of these. "materials" is a
#: word on its own because two of the sample papers title the section "MATERIALS AND METHODS"
#: and a third "Experimental Procedures" -- and no `sec-type` is reliable enough to use alone.
_METHODS_WORDS = ("method", "materials", "experimental procedure")

#: Units a paragraph's text must not swallow: each becomes passages of its own, so leaving its
#: text in the enclosing `<p>` would make every table cell quotable twice, once with headers and
#: once without. A nested `<p>` (list items, boxed text, footnotes) is a unit of its own for the
#: same reason. The tail text after such an element still belongs to the paragraph.
_OWN_UNITS = frozenset(
    {"table-wrap", "table-wrap-group", "fig", "fig-group", "p", "boxed-text", "fn"}
)

#: Elements whose `<p>` children are emitted by the unit that owns them, not as paragraphs.
_OWNING_CONTAINERS = frozenset({"caption", "table-wrap", "table-wrap-group", "fig", "fig-group"})


class JatsUnreadable(ValueError):
    """The bytes are not a JATS article: not XML, or XML whose root is not `<article>`."""


@dataclass(frozen=True, slots=True)
class Passage:
    id: str
    text: str
    kind: str
    """One of `p`, `td`, `caption`, `title`."""
    section_path: tuple[str, ...]
    """Titles of the enclosing sections, outermost first; for a cell or caption, the table or
    figure label comes last."""
    row_headers: tuple[str, ...] = ()
    column_headers: tuple[str, ...] = ()

    def location(self) -> Location:
        return Location(
            passage_id=self.id,
            section_path=self.section_path,
            kind=self.kind,
            row_headers=self.row_headers,
            column_headers=self.column_headers,
        )


@dataclass(frozen=True, slots=True)
class Document:
    article_type: str
    title: str
    pmcid: str
    pmid: str
    doi: str
    year: int | None
    passages: tuple[Passage, ...]
    has_methods_section: bool
    supplementary: tuple[str, ...]
    tables: tuple[TableView, ...] = ()
    """Every table whole, in document order, each cell naming the passage it became. The
    cells are the passages; this is the layout around them, for the review page (ADR-0940)."""

    def passage(self, passage_id: str) -> Passage | None:
        return next((p for p in self.passages if p.id == passage_id), None)

    def table_holding(self, passage_id: str) -> TableView | None:
        return next((table for table in self.tables if table.holds(passage_id)), None)

    def text(self) -> str:
        """Every passage, one per line, for a search over the whole paper."""
        return "\n".join(passage.text for passage in self.passages)


def read_jats(xml: str) -> Document:
    """Parse one Europe PMC full-text response.

    lxml refuses a `str` that carries an encoding declaration, and half the fixtures do, so the
    text is encoded back to bytes first; the declaration is then honoured rather than fought.
    The parser loads no DTD and resolves no entity: the DOCTYPE these files carry names a
    network resource, and a reader of third-party XML must not follow it.
    """
    parser = etree.XMLParser(
        load_dtd=False, no_network=True, resolve_entities=False, huge_tree=True, recover=False
    )
    try:
        root = etree.fromstring(xml.encode("utf-8"), parser)
    except etree.XMLSyntaxError as error:
        raise JatsUnreadable(f"not well-formed XML: {error}") from error
    if root.tag != "article":
        raise JatsUnreadable(f"root element is <{root.tag}>, not <article>")

    meta = root.find("front/article-meta")
    reader = _Reader()
    if meta is not None:
        # The abstract is front matter, but it is prose the model should read and quote from,
        # and one sample paper's abstract holds the number the rest of the paper qualifies.
        for abstract in meta.findall("abstract"):
            title = abstract.find("title")
            heading = _text(title) if title is not None else "Abstract"
            reader.walk(abstract, (heading or "Abstract",))
    for part in ("body", "floats-group"):
        # `<back>` is optional and never read: it holds the reference list, acknowledgements and
        # footnotes, and a number quoted from there is a number the paper did not measure.
        # `<floats-group>` is where older archive files park the tables and figures the body
        # refers to, so leaving it out would drop exactly the cells this reader exists for.
        element = root.find(part)
        if element is not None:
            reader.walk(element, ())

    return Document(
        article_type=root.get("article-type") or "",
        title=_text(meta.find("title-group/article-title")) if meta is not None else "",
        pmcid=_pmcid(meta),
        pmid=_article_id(meta, "pmid"),
        doi=_article_id(meta, "doi"),
        year=_year(meta),
        passages=tuple(reader.passages),
        has_methods_section=any(_is_methods_title(title) for title in reader.section_titles),
        supplementary=_supplementary(root),
        tables=tuple(reader.tables),
    )


def render_for_model(doc: Document) -> str:
    """One line per passage, each opening with the id the model is asked to quote by.

    A cell renders its headers before its text so the model reads the property and the condition
    with the number, the way a reader of the printed table does. The format is the whole contract
    with the instruction in `extraction.py`, and it has to be byte-identical across calls for the
    same XML or the cached prefix is bought again.
    """
    lines = []
    for passage in doc.passages:
        where = " > ".join(passage.section_path)
        if passage.kind == "td":
            body = (
                f"row: {' / '.join(passage.row_headers)} | "
                f"column: {' / '.join(passage.column_headers)} | cell: {passage.text}"
            )
        else:
            body = passage.text
        lines.append(f"[{passage.id}] {where} :: {body}")
    return "\n".join(lines)


class _Reader:
    """One traversal in document order, numbering each kind of unit as it is met."""

    def __init__(self) -> None:
        self.passages: list[Passage] = []
        self.tables: list[TableView] = []
        self.section_titles: list[str] = []
        self._paragraphs = 0
        self._sections = 0
        self._tables = 0
        self._figures = 0

    def walk(self, element: etree._Element, path: tuple[str, ...]) -> None:
        for child in element:
            tag = child.tag
            if not isinstance(tag, str):
                continue  # a comment or processing instruction, which lxml yields as children
            if tag == "sec":
                self._section(child, path)
            elif tag == "p":
                if not self._owned(child):
                    self._paragraph(child, path)
                # A paragraph can wrap a table, a figure or a list: those are units of their own
                # and are found by walking into it, having been left out of its text above.
                self.walk(child, path)
            elif tag in ("table-wrap", "table-wrap-group"):
                self._table_wrap(child, path)
            elif tag in ("fig", "fig-group"):
                self._figure(child, path)
            elif tag != "title":
                self.walk(child, path)

    @staticmethod
    def _owned(paragraph: etree._Element) -> bool:
        """Is this `<p>` inside a caption, table or figure, whose own unit emits it?"""
        return any(ancestor.tag in _OWNING_CONTAINERS for ancestor in paragraph.iterancestors())

    def _section(self, sec: etree._Element, path: tuple[str, ...]) -> None:
        self._sections += 1
        title = sec.find("title")
        heading = _text(title) if title is not None else ""
        if heading:
            self.section_titles.append(heading)
            self.passages.append(
                Passage(id=f"s{self._sections}title", text=heading, kind="title", section_path=path)
            )
        # An untitled section adds nothing to the path: a level nobody could name is not a
        # location a reviewer can find.
        self.walk(sec, path + (heading,) if heading else path)

    def _paragraph(self, paragraph: etree._Element, path: tuple[str, ...]) -> None:
        self._paragraphs += 1
        text = _text(paragraph, skip=_OWN_UNITS)
        if text:
            self.passages.append(
                Passage(id=f"p{self._paragraphs}", text=text, kind="p", section_path=path)
            )

    def _figure(self, fig: etree._Element, path: tuple[str, ...]) -> None:
        self._figures += 1
        label = _text(fig.find("label"))
        self._caption(fig, f"fig{self._figures}cap", path + (label,) if label else path)
        for nested in fig.findall("fig"):
            # A `<fig-group>` holds several figures, each with its own caption and label.
            self._figure(nested, path)

    def _table_wrap(self, wrap: etree._Element, path: tuple[str, ...]) -> None:
        if wrap.tag == "table-wrap-group":
            for nested in wrap.findall("table-wrap"):
                self._table_wrap(nested, path)
            return
        self._tables += 1
        table_index = self._tables
        label = _text(wrap.find("label"))
        table_path = path + (label,) if label else path
        self._caption(wrap, f"t{table_index}cap", table_path)

        # Which passage each cell element became, so the whole-table view below can name them.
        # The elements are held here for the duration, which is what keeps lxml handing back
        # the same proxy objects when the rows are walked a second time.
        became: dict[etree._Element, str] = {}
        row_number = 0
        for table in wrap.iter("table"):
            for row in _Grid(table).body_rows():
                row_number += 1
                headers = tuple(_text(cell) for cell in row.header_cells)
                cells = row.data_cells
                if not row.header_cells and cells:
                    # No `<th>` on the row: the first cell is its label, and the other cells
                    # read as "<label>, <column header>". The label cell itself is still a
                    # passage, headed by nothing, so a value that was put there can be quoted.
                    label_cell, *cells = cells
                    self._cell(
                        label_cell, table_index, row_number, (), table_path, row.columns, became
                    )
                    headers = (_text(label_cell[1]),)
                for column, cell in cells:
                    self._cell(
                        (column, cell),
                        table_index,
                        row_number,
                        headers,
                        table_path,
                        row.columns,
                        became,
                    )
        self.tables.append(_table_view(wrap, label, became))

    def _cell(
        self,
        placed: tuple[int, etree._Element],
        table_index: int,
        row_number: int,
        row_headers: tuple[str, ...],
        table_path: tuple[str, ...],
        columns: tuple[tuple[str, ...], ...],
        became: dict[etree._Element, str],
    ) -> None:
        column, cell = placed
        text = _text(cell)
        if not text:
            return  # an empty cell has nothing to quote, and skipping it leaves the ids positional
        passage_id = f"t{table_index}r{row_number}c{column + 1}"
        became[cell] = passage_id
        self.passages.append(
            Passage(
                id=passage_id,
                text=text,
                kind="td",
                section_path=table_path,
                row_headers=row_headers,
                column_headers=columns[column] if column < len(columns) else (),
            )
        )

    def _caption(self, owner: etree._Element, passage_id: str, path: tuple[str, ...]) -> None:
        text = _caption_text(owner)
        if text:
            self.passages.append(
                Passage(id=passage_id, text=text, kind="caption", section_path=path)
            )


def _caption_text(owner: etree._Element) -> str:
    caption = owner.find("caption")
    if caption is None:
        return ""
    parts = [_text(child) for child in caption if isinstance(child.tag, str)]
    return " ".join(part for part in parts if part)


def _table_view(wrap: etree._Element, label: str, became: dict[etree._Element, str]) -> TableView:
    """The table as printed: every `<tr>` with its cells and their spans, header rows first
    because that is where the archive puts them, and the footnotes the markers point at."""
    rows = []
    for tr in wrap.iter("tr"):
        cells = tuple(
            TableCell(
                text=_text(cell),
                header=cell.tag == "th" or _in_head(tr),
                colspan=_span(cell.get("colspan")),
                rowspan=_span(cell.get("rowspan")),
                passage_id=became.get(cell, ""),
            )
            for cell in tr
            if cell.tag in ("td", "th")
        )
        rows.append(cells)
    return TableView(
        label=label,
        caption=_caption_text(wrap),
        foot=_text(wrap.find("table-wrap-foot")),
        rows=tuple(rows),
    )


@dataclass(frozen=True, slots=True)
class _Row:
    header_cells: tuple[etree._Element, ...]
    """The `<th>` cells that cover this row, including one spanning down from an earlier row."""
    data_cells: tuple[tuple[int, etree._Element], ...]
    """(grid column, cell) for each `<td>` that starts on this row."""
    columns: tuple[tuple[str, ...], ...]
    """Column headers by grid column: one entry per `<thead>` row, colspan expanded."""


class _Grid:
    """Cells laid on the grid a browser would draw, so a column index survives colspan and
    rowspan. Header rows are those under `<thead>`; every other row is a body row, whatever
    element wraps it, because archive files do not agree on `<tbody>`."""

    def __init__(self, table: etree._Element) -> None:
        self._head: list[dict[int, etree._Element]] = []
        self._body: list[dict[int, etree._Element]] = []
        self._starts: list[set[int]] = []
        self._place(table)

    def _place(self, table: etree._Element) -> None:
        # Cells a rowspan carries down into later rows, keyed by row index then grid column. A
        # carried cell occupies its slot -- the next cell in that row shifts right past it -- and
        # a carried `<th>` still heads the row it reaches, which is how a merged row label
        # covers every row it spans.
        carried: dict[int, dict[int, etree._Element]] = {}
        for index, row in enumerate(table.iter("tr")):
            placed = dict(carried.pop(index, {}))
            starts: set[int] = set()
            column = 0
            for cell in row:
                if cell.tag not in ("td", "th"):
                    continue
                while column in placed:
                    column += 1
                starts.add(column)
                for dc in range(_span(cell.get("colspan"))):
                    placed[column + dc] = cell
                    for dr in range(1, _span(cell.get("rowspan"))):
                        carried.setdefault(index + dr, {})[column + dc] = cell
                column += _span(cell.get("colspan"))
            if _in_head(row):
                self._head.append(placed)
            else:
                self._body.append(placed)
                self._starts.append(starts)

    def body_rows(self) -> list[_Row]:
        width = max((max(row, default=-1) for row in self._head + self._body), default=-1) + 1
        columns = tuple(
            tuple(_text(row[c]) for row in self._head if c in row and _text(row[c]))
            for c in range(width)
        )
        rows = []
        for placed, starts in zip(self._body, self._starts, strict=True):
            headers: list[etree._Element] = []
            data = []
            for column in sorted(placed):
                cell = placed[column]
                if cell.tag == "th":
                    if cell not in headers:
                        headers.append(cell)
                elif column in starts:
                    data.append((column, cell))
            rows.append(_Row(tuple(headers), tuple(data), columns))
        return rows


def _in_head(row: etree._Element) -> bool:
    return any(ancestor.tag == "thead" for ancestor in row.iterancestors())


def _span(value: str | None) -> int:
    try:
        return max(1, int(value)) if value else 1
    except ValueError:
        return 1


def _text(element: etree._Element | None, skip: frozenset[str] = frozenset()) -> str:
    """The element's text with inline markup flattened and whitespace collapsed.

    Not `itertext()`, because two things must happen on the way: a bibliographic `<xref>` is
    replaced by its token, a `<sup>` keeps its meaning (`_SUPERSCRIPT`), and an element in
    `skip` contributes nothing but its tail. Nothing is folded here -- both micro signs and
    en-dashes pass through as written, since folding is the comparison's business
    (`quotes.fold`) and a reviewer should see the paper's own characters.
    """
    if element is None:
        return ""
    return _WHITESPACE.sub(" ", "".join(_pieces(element, skip))).strip()


def _pieces(element: etree._Element, skip: frozenset[str]):
    if element.text:
        yield element.text
    for child in element:
        if isinstance(child.tag, str):
            if child.tag == "xref" and child.get("ref-type") == "bibr":
                inner = _WHITESPACE.sub(" ", "".join(child.itertext())).strip()
                yield f"[ref {inner or child.get('rid', '')}]"
            elif child.tag == "sup":
                yield _superscript("".join(_pieces(child, skip)))
            elif child.tag not in skip:
                yield from _pieces(child, skip)
        if child.tail:
            yield child.tail


def _superscript(text: str) -> str:
    """The text of a `<sup>` as it reaches the passage: see `_SUPERSCRIPT`."""
    inner = _WHITESPACE.sub(" ", text).strip()
    if not inner:
        return ""
    # A minus sign or a hyphen inside an exponent both mean minus; the superscript minus is
    # the one character, and `quotes.fold` maps it to `^-`.
    plain = inner.replace(chr(0x2212), "-")
    if _SUPERSCRIPTABLE.match(plain):
        return plain.translate(_SUPERSCRIPT)
    return "^" + inner


def _is_methods_title(title: str) -> bool:
    folded = title.casefold()
    # "Supplementary Materials" is the title Europe PMC gives the associated-data section, and
    # a "Supplementary Methods" heading points at material this prototype does not read. Both
    # would pass the word test and admit a paper that measured nothing in its own text
    # (PMC13340094 is the sample that forced this clause).
    if "supplement" in folded:
        return False
    return any(word in folded for word in _METHODS_WORDS)


def _article_id(meta: etree._Element | None, kind: str) -> str:
    if meta is None:
        return ""
    for article_id in meta.findall("article-id"):
        if article_id.get("pub-id-type") == kind:
            return (article_id.text or "").strip()
    return ""


def _pmcid(meta: etree._Element | None) -> str:
    value = _article_id(meta, "pmcid") or _article_id(meta, "pmc")
    if value and not value.upper().startswith("PMC"):
        value = f"PMC{value}"
    return value


def _year(meta: etree._Element | None) -> int | None:
    if meta is None:
        return None
    for year in meta.iterfind("pub-date/year"):
        digits = (year.text or "").strip()
        if digits.isdigit():
            return int(digits)
    return None


def _supplementary(root: etree._Element) -> tuple[str, ...]:
    """Every file the article points at as supplementary, each once, in document order.

    Europe PMC lists the same media under the body's section and again under the
    associated-data section, so a naive collection reports each file twice.
    """
    seen: list[str] = []
    for material in root.iter("supplementary-material"):
        for element in material.iter():
            href = element.get(_XLINK_HREF)
            if href and href not in seen:
                seen.append(href)
    return tuple(seen)
