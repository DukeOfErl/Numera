"""The entries table an answer is presented with.

Selection and ordering live here because every driver needs the same ones; the
rendering does not, because a terminal and a browser have nothing in common there.
The reference is looked up here rather than carried through the agent: it is
presentation, and at a median 183 characters it would more than double what a
50-row search costs if it reached the model.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from typing import Any

from . import bionumbers, objections, references, trust_marks
from .corpus import EntryId, Origin
from .repository import CorpusRepository
from .units import dimensions_of

# Column order and relative widths follow the reference database's results page,
# so output can be compared against it by eye. Two text lines per row, cells
# wrapped and then truncated, as there.
COLUMNS: tuple[tuple[str, str, int], ...] = (
    ("property", "Property", 29),
    # 17, not 15: almost every organism reads "Group Genus species", and at 15 the
    # species truncates on every single row, which the reference page does not do.
    ("organism", "Organism", 17),
    ("value", "Value", 13),
    ("units", "Units", 12),
    ("entry_id", "ID", 7),
    ("reference", "Reference", 18),
)
LINES_PER_ROW = 2
TERMINAL_ROWS = 5

# Marks an entry whose measurement method the corpus does not record. A textbook
# page and a measurement over a thousand cells otherwise look identical in a
# table, and the difference is what a reader is here to judge. The absence is all
# that is claimed: nothing here grades an entry that does record one.
NO_METHOD = "\u2020"
NO_METHOD_LEGEND = f"{NO_METHOD} no measurement method recorded"

# Marks a row the answer cited but no tool call returned -- the entry exists, so
# nothing about the row looks wrong, and that is exactly the problem. Without the
# mark it sits among the cited entries as though the answer rested on it legitimately.
NOT_RETRIEVED = "\u2021"
NOT_RETRIEVED_LEGEND = f"{NOT_RETRIEVED} cited but not retrieved during this question"

# Marks an entry the corpus holds without a scalar value -- a table link, or a
# figure that lives only in the comments. Spelled once in a legend rather than
# repeated in every such row, where it crowds out the values that are there.
NO_SCALAR = "\u00a7"
NO_SCALAR_LEGEND = f"{NO_SCALAR} no scalar value recorded"
# "Possibly relevant" because these rows are ranked, not left in retrieval order:
# they are the entries whose wording is closest to the question and the cited
# properties. Saying only what they are not would invite reading them as noise.
UNCITED_BANNER = "possibly relevant (not cited in the answer)"
# Said where the cited table would be. An answer that cited nothing and a table
# that simply started with uncited rows looked the same, and they are not.
NOTHING_CITED = "No entries cited"

# Marks a value the source hedged. `<8` reaches the corpus as the interval [8, 8]
# and prints as "8.0", which asserts an equality the source never made -- and a
# bound is a different claim, not a rounder one: an MIC of `<8` means susceptible
# at or below 8. Measured live before this existed: the agent answered "the minimal
# inhibitory concentration of kanamycin for E. coli is 8.0 mg/L" (BNID 100763),
# with the table agreeing, so nothing on the page contradicted anything. 2,233
# entries carry it, and they concentrate in the well-known quantities people ask
# about, so the flag is denser in the answered population than in the stored one.
QUALIFIED = "\u00b0"
QUALIFIED_LEGEND = f"{QUALIFIED} the source stated a bound or an approximation, not an exact range"

# Marks a range whose bounds may have come from two different quantities: the
# ingester takes the smallest and largest number in a cell, so a generation time
# sitting beside a width becomes one plausible-looking interval. 1,461 entries.
FUSED = "\u2248"
FUSED_LEGEND = f"{FUSED} the two bounds may describe different quantities"

# Marks a range spanning further than any single measurement plausibly does. The
# rule and its threshold live on `Entry` (corpus.py), because the model is told
# about it too and the agent must not reach into a presentation module for it.
IMPLAUSIBLE = "\u00a1"
IMPLAUSIBLE_LEGEND = (
    f"{IMPLAUSIBLE} the bounds span more than a millionfold, which no single measurement does"
)

# Marks a harvested value whose numbers could not be read with certainty: the paper's own words
# are shown and no number is stated for it (ADR-1620).
READING_UNCERTAIN = "?"
READING_UNCERTAIN_LEGEND = (
    f"{READING_UNCERTAIN} the value could not be read as a number with certainty; "
    "the paper's own words are shown"
)

# Marks a harvested value the paper calculated rather than measured, from its own numbers or from
# values published elsewhere.
CALCULATED = "\u2234"
CALCULATED_LEGEND = f"{CALCULATED} calculated, not measured"

# Words that carry no topic. Kept small on purpose -- this is a tie-breaker for
# rows nobody cited, not a retrieval engine.
_STOPWORDS = frozenset(
    "the of a an in on at and or is are was were for to from with by what "
    "which its their per between during under over into".split()
)


# The corpus carries injected markup in `keywords` on 10,206 of its 14,294
# entries -- `<IMG SRC="/WF_SQL_XSRF.html">`, an artefact of the source export.
# Stripped for display only: the corpus is an external input this project does
# not correct, and the fix belongs to whatever produces the file. Not stripped at
# load, which would silently change what the search index matches on.
_MARKUP_RE = re.compile(r"<[^>]*>")


def _without_markup(text: str) -> str:
    return _MARKUP_RE.sub("", text).strip()


def _topic_words(text: str) -> frozenset[str]:
    return frozenset(
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) > 2 and word not in _STOPWORDS
    )


@dataclass(frozen=True)
class Row:
    entry_id: EntryId
    property: str
    organism: str
    value: str
    units: str
    reference: str
    cited: bool
    method_recorded: bool = True
    retrieved: bool = True
    has_scalar: bool = True
    method: str = ""
    # Not shown in the terminal's columns, which follow the reference database's
    # results page. Carried so a driver that can open a row -- the web page -- has
    # the whole entry without holding the repository to look it up again, and so a
    # transcript of what was drawn can be redrawn on its own.
    comments: str = ""
    keywords: tuple[str, ...] = ()
    reference_pubmed_id: str = ""
    qualified: bool = False
    fused: bool = False
    implausible_span: bool = False
    # Only for an entry read from the harvest store; a corpus-file row leaves all three at their
    # defaults and draws exactly as before.
    reading_uncertain: bool = False
    calculated: bool = False
    trust: Any = None
    # What objecting reviewers said, for a disputed entry from the store: shown to a reader who
    # asks why, never to the model (`objections`).
    objections: tuple[str, ...] = ()
    # The harvested value's own fields, for the full entry: its keywords pack the quote and every
    # condition's quote together for search, so drawn as keywords they read as one fused field.
    harvest: Any = None
    # First author and year, for the web table's grey line under the property (ADR-1850); "" where
    # the reference does not give them with certainty.
    short_reference: str = ""

    @property
    def stars(self) -> str:
        return trust_marks.stars(self.trust)

    @property
    def trust_cell(self) -> str:
        """The stars, then what objecting reviewers said: a double click opens it in full."""
        if not self.objections:
            return self.stars
        return f"{self.stars} {' · '.join(self.objections)}"

    def markers(self) -> str:
        # Deliberately not `has_scalar`: the terminal writes "(no scalar value)"
        # in the value column, so a marker there would say it twice. The web
        # driver blanks that column and adds the marker itself.
        applying = (
            (NOT_RETRIEVED, not self.retrieved),
            (NO_METHOD, not self.method_recorded),
            (QUALIFIED, self.qualified),
            (FUSED, self.fused),
            (IMPLAUSIBLE, self.implausible_span),
            (READING_UNCERTAIN, self.reading_uncertain),
            (CALCULATED, self.calculated),
        )
        return "".join(mark for mark, applies in applying if applies)

    def cell(self, field: str) -> str:
        if field == "markers":
            return self.markers()
        return str(getattr(self, field))


def _relevance(repo: CorpusRepository, cited: tuple[EntryId, ...], question: str):
    """Score an uncited entry by how much of the topic's wording its property shares.

    The topic is the question plus the properties of the entries the answer cited:
    the question alone is too thin to separate "Cell diameter" from "Diameter of
    flagella", while the cited properties say which object the answer settled on.
    Words already in the row's own organism are discounted, since the organism was
    matched before the search ran and repeating it in a property says nothing --
    without that, "Diameter of fimbriae of E. coli" outranks every cell entry.

    Deliberately crude, and known to be. It sinks the entries that are plainly
    about another object, which is what it is for; it cannot tell a flagellum from
    a cell, because no amount of string overlap knows any biology.
    """
    vocabulary = _topic_words(question)
    for entry_id in cited:
        found = repo.get(entry_id)
        if found is not None:
            vocabulary |= _topic_words(found.entry.property)

    def score(entry_id: EntryId) -> int:
        found = repo.get(entry_id)
        if found is None:  # pragma: no cover - filtered before scoring
            return 0
        entry = found.entry
        return len((_topic_words(entry.property) - _topic_words(entry.organism)) & vocabulary)

    return score


def rows_for(
    repo: CorpusRepository,
    cited: tuple[EntryId, ...],
    retrieved: tuple[EntryId, ...],
    question: str = "",
) -> tuple[Row, ...]:
    """Cited entries first, then the rest by how close their wording is to the topic.

    Cited first because those are the ones the answer stands on, and a reader
    checking prose against a table should not have to hunt for them. The rest are
    ranked rather than left in retrieval order, which for a single search is the
    corpus's own identifier order and so carries no relevance at all -- it is what
    put a 490 um chromosome in the top five of a question about a 1 um cell.
    """
    ordered: list[EntryId] = [b for b in cited if repo.get(b) is not None]
    seen = set(ordered)
    rest = []
    for entry_id in retrieved:
        if entry_id not in seen and repo.get(entry_id) is not None:
            rest.append(entry_id)
            seen.add(entry_id)
    score = _relevance(repo, cited, question)
    # Stable, so entries the score cannot separate stay in the order they were met.
    rest.sort(key=lambda entry_id: -score(entry_id))
    ordered += rest

    out = []
    for entry_id in ordered:
        found = repo.get(entry_id)
        if found is None:  # pragma: no cover - filtered above
            continue
        entry = found.entry
        out.append(
            Row(
                entry_id=entry.entry_id,
                property=entry.property,
                organism=entry.organism,
                value=entry.value_display,
                units=entry.units,
                reference=_reference(entry),
                cited=entry_id in cited,
                method_recorded=bool(entry.measurement_method.strip()),
                # A harvested value always has the paper's own words to show, read or not: its
                # `?` mark says when no number was taken from them.
                has_scalar=entry.value is not None
                or entry.range_low is not None
                or entry.range_high is not None
                or entry.harvest is not None,
                retrieved=entry_id in retrieved,
                method=" ".join(entry.measurement_method.split()),
                comments=entry.comments,
                keywords=tuple(_without_markup(k) for k in entry.keywords),
                reference_pubmed_id=entry.reference_pubmed_id or "",
                qualified=entry.range_qualified,
                fused=entry.range_fused,
                implausible_span=entry.spans_implausibly,
                reading_uncertain=entry.harvest is not None and entry.harvest.reading_uncertain,
                calculated=entry.harvest is not None
                and entry.harvest.origin is not Origin.MEASURED,
                trust=entry.trust,
                objections=objections.of(repo, entry.record_id)
                if entry.trust is not None and entry.trust.disputed
                else (),
                harvest=entry.harvest,
                short_reference=_short_reference(entry),
            )
        )
    return tuple(out)


def _reference(entry) -> str:
    """Chicago author-date where the store holds the paper's record (ADR-1640), else as stored."""
    if entry.harvest is not None:
        return references.chicago(entry.harvest.paper.csl_json) or entry.reference
    return entry.reference


def _short_reference(entry) -> str:
    """First author and year: from the paper's record for a harvested entry, else from the
    reference string BioNumbers wrote (ADR-1850)."""
    if entry.harvest is not None:
        return references.short(entry.harvest.paper.csl_json)
    return references.short_from_bionumbers(entry.reference or "")


def _cell_lines(text: str, width: int) -> list[str]:
    """Wrapped to at most two lines, the second truncated with an ellipsis.

    Truncating rather than wrapping further keeps every row the same height, which
    is what makes a long table scannable and what the reference page does.

    A single token is never broken across lines. "6800.0-72000.0" is one character
    wider than the value column, and split it read as "6800.0-72000." above a lone
    "0" -- a value the corpus does not hold, shown without any sign that it had been
    altered. An ellipsis at least says that something was cut.
    """
    wrapped = textwrap.wrap(text, width=width, break_long_words=False) or [""]
    lines = wrapped[:LINES_PER_ROW]
    if len(wrapped) > LINES_PER_ROW and width >= 2:
        lines[-1] = lines[-1][: width - 1].rstrip() + "…"
    # With long words kept whole, a line may still overrun the column and would
    # push every column after it out of alignment.
    if width >= 2:
        lines = [line if len(line) <= width else line[: width - 1] + "…" for line in lines]
    return lines + [""] * (LINES_PER_ROW - len(lines))


def summarise(shown: int, retrieved: int, matched: int = 0, searches: int = 0) -> str:
    """The line under the table: what is shown, what was retrieved, what matched.

    Three numbers, because each answers a different question. Shown is what fits.
    Retrieved is how many entries the agent actually had. Matched is how many the
    corpus held, and it is the one worth having: when a search hits the row cap,
    matched is the size of what was never looked at, and a table reporting only
    the first two reads as though the corpus had nothing more.
    """
    if not retrieved:
        return ""
    parts = [f"showing {shown} of {retrieved} entries retrieved"]
    # Equal means every match was retrieved, so nothing was left unlooked-at and
    # the second number would only repeat the first.
    if searches and matched != retrieved:
        # Stated as a per-search sum rather than a union: beyond the row cap the
        # identities are unknown, so the entries two searches share cannot be
        # counted once. Naming the number of searches is what keeps that honest.
        across = f" across {searches} searches" if searches > 1 else ""
        parts.append(f"{matched} matched{across}")
    return "… " + "; ".join(parts)


def dimension_note(rows: tuple[Row, ...]) -> str | None:
    """What kinds of quantity the cited entries measure, when they measure more than one.

    Over every cited row, not only the shown ones: the answer rests on all of
    them. Stated as a fact about the units rather than as a fault, because citing
    a length and a mass together is often exactly right -- what is wrong is
    reading them as one another's alternatives.
    """
    spanned = dimensions_of([row.units for row in rows if row.cited])
    if len(spanned) <= 1:
        return None
    return (
        f"cited entries measure {len(spanned)} kinds of quantity "
        f"({', '.join(spanned)}) -- not alternatives for one another"
    )


def _banner(width: int) -> str:
    """A dashed rule naming what follows, so the break is not read as the table ending."""
    label = f" {UNCITED_BANNER} "
    fill = max(0, width - len(label))
    left = fill // 2
    return "-" * left + label + "-" * (fill - left)


def _methods_block(shown: tuple[Row, ...], width: int) -> list[str]:
    """How each cited entry was measured, where the corpus records it.

    Rule 4 asks an answer that reports differing values to say what distinguishes
    them, and the conditions are the answer to that. Until now the table said only
    when a method was *absent*: a textbook page and a count over a thousand cells
    were both just rows, and a reader could not check the prose's claim about why
    two entries differ. One entry cited on its own needs no distinguishing, so this
    starts at two.

    First line only. The median recorded method is 231 characters and the longest
    2,382, which no terminal table can carry -- but the opening phrase is what
    separates "Transmission electron microscopy" from "Coulter counter" from a
    caption to a figure, which is exactly the distinction being drawn.
    """
    cited = [row for row in shown if row.cited and row.method]
    if len(cited) < 2:
        return []
    out = ["how the cited entries were measured:"]
    for row in cited:
        prefix = f"  {bionumbers.label(row.entry_id)}  "
        out.append(prefix + _clamp(row.method, width - len(prefix)))
    return out


def _objections_block(shown: tuple[Row, ...], width: int) -> list[str]:
    """What reviewers said against each shown entry they disputed.

    The page puts this after the stars, where a double click opens it; a terminal cannot open a
    cell, so it is listed here, one line an objection, cut to the table.
    """
    disputed = [row for row in shown if row.objections]
    if not disputed:
        return []
    out = ["objections raised:"]
    for row in disputed:
        prefix = f"  {bionumbers.label(row.entry_id)}  "
        out += [prefix + _clamp(said, width - len(prefix)) for said in row.objections]
    return out


def _clamp(text: str, width: int) -> str:
    """One line, cut at a word where it can be, with the cut marked."""
    if len(text) <= width or width < 2:
        return text[:width]
    cut = text[: width - 1]
    spaced = cut.rsplit(" ", 1)[0]
    # Only back up to a word boundary when that leaves most of the line; a very
    # long first word would otherwise collapse the cell to almost nothing.
    if len(spaced) >= width // 2:
        cut = spaced
    return cut.rstrip(" ,;:") + "\u2026"


def render(
    rows: tuple[Row, ...],
    limit: int = TERMINAL_ROWS,
    total: int | None = None,
    matched: int = 0,
    searches: int = 0,
) -> str:
    """The table as text. Empty when there is nothing to show.

    Nothing here comes from the model. Every cell is read from the corpus, and the
    only thing the answer influences is which rows come first -- a cited
    identifier the corpus does not hold produces no row at all, so the table
    cannot show something that was made up.
    """
    if not rows:
        return ""
    shown = rows[:limit]
    columns = _columns(shown)
    rule = "  ".join("-" * width for _, _, width in columns)
    header = "  ".join(title.ljust(width) for _, title, width in columns).rstrip()
    out = [header, rule]
    # Nothing cited draws no transition, so without this the table renders exactly
    # as one whose top rows are the cited ones -- and a reader would take the first
    # row for the citation, because everywhere else it is. Said where the cited
    # rows would have been.
    if not shown[0].cited:
        out.append(NOTHING_CITED)
        out.append(_banner(len(rule)))
    for index, row in enumerate(shown):
        if index and shown[index - 1].cited and not row.cited:
            # A reader checking the prose needs the entries it rests on separated
            # from the ones it does not. The rest are still shown, because what the
            # corpus held and the answer passed over is part of the evidence.
            out.append(_banner(len(rule)))
        cells = [_cell_lines(row.cell(field), width) for field, _, width in columns]
        for line_number in range(LINES_PER_ROW):
            line = "  ".join(
                cells[i][line_number].ljust(width) for i, (_, _, width) in enumerate(columns)
            ).rstrip()
            if line:
                out.append(line)
    retrieved = total if total is not None else len(rows)
    if retrieved > len(shown) or matched > len(shown):
        out.append(summarise(len(shown), retrieved, matched, searches))
    note = dimension_note(rows)
    if note:
        # Wrapped to the table, because the number of dimensions is unbounded and
        # a footnote running past the rule reads as a line of a different table.
        out.extend(textwrap.wrap(note, len(rule), subsequent_indent="  "))
    out.extend(_methods_block(shown, len(rule)))
    out.extend(_objections_block(shown, len(rule)))
    if any(not row.retrieved for row in shown):
        out.append(NOT_RETRIEVED_LEGEND)
    if any(not row.method_recorded for row in shown):
        out.append(NO_METHOD_LEGEND)
    if any(row.qualified for row in shown):
        out.append(QUALIFIED_LEGEND)
    if any(row.fused for row in shown):
        out.append(FUSED_LEGEND)
    if any(row.implausible_span for row in shown):
        out.extend(textwrap.wrap(IMPLAUSIBLE_LEGEND, len(rule), subsequent_indent="  "))
    if any(row.reading_uncertain for row in shown):
        out.append(READING_UNCERTAIN_LEGEND)
    if any(row.calculated for row in shown):
        out.append(CALCULATED_LEGEND)
    for line in trust_marks.legend((row.trust for row in shown), terminal=True):
        out.extend(textwrap.wrap(line, len(rule), subsequent_indent="  "))
    return "\n".join(out)


def _columns(shown: tuple[Row, ...]) -> tuple[tuple[str, str, int], ...]:
    """The columns to draw: the caveat marks first, then the reference page's, trust before the ID.

    The marks have a narrow column of their own, headed by nothing, rather than a prefix on the
    property (`grounded-answering`): a reader scanning properties no longer reads past symbols,
    and the marks line up. As wide as the most marks any shown row carries. The trust column
    appears only where some entry has a tier, so a corpus-file table gains nothing but the marks.
    """
    marks = ("markers", "", max(1, *(len(row.markers()) for row in shown)))
    # The identifier is the cell a reader checks against the prose, and a terminal cannot open a
    # truncated cell: two labels cut to `PMC265…` were indistinguishable in the first live run
    # over the store (2026-10-16). So the column is as wide as the longest identifier shown; a
    # corpus file's BNIDs fit the default and draw exactly as before.
    widest = max(len(str(row.entry_id)) for row in shown)
    columns = [
        marks,
        *(
            (field, title, max(width, widest) if field == "entry_id" else width)
            for field, title, width in COLUMNS
        ),
    ]
    if any(row.trust is not None for row in shown):
        # Before the identifier, after the units: the order both drivers draw (2026-10-16).
        at = [field for field, _, _ in columns].index("entry_id")
        columns.insert(at, ("stars", "Trust", 7))
    return tuple(columns)
