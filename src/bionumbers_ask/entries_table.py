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

from .repository import CorpusRepository

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
    ("bnid", "ID", 7),
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
UNCITED_BANNER = "not cited in the answer"

# Words that carry no topic. Kept small on purpose -- this is a tie-breaker for
# rows nobody cited, not a retrieval engine.
_STOPWORDS = frozenset(
    "the of a an in on at and or is are was were for to from with by what "
    "which its their per between during under over into".split()
)


def _topic_words(text: str) -> frozenset[str]:
    return frozenset(
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) > 2 and word not in _STOPWORDS
    )


@dataclass(frozen=True)
class Row:
    bnid: int
    property: str
    organism: str
    value: str
    units: str
    reference: str
    cited: bool
    method_recorded: bool = True
    retrieved: bool = True

    def markers(self) -> str:
        applying = (
            (NOT_RETRIEVED, not self.retrieved),
            (NO_METHOD, not self.method_recorded),
        )
        return "".join(mark for mark, applies in applying if applies)

    def cell(self, field: str) -> str:
        return str(getattr(self, field))


def _relevance(repo: CorpusRepository, cited: tuple[int, ...], question: str):
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
    for bnid in cited:
        found = repo.get(bnid)
        if found is not None:
            vocabulary |= _topic_words(found.entry.property)

    def score(bnid: int) -> int:
        found = repo.get(bnid)
        if found is None:  # pragma: no cover - filtered before scoring
            return 0
        entry = found.entry
        return len((_topic_words(entry.property) - _topic_words(entry.organism)) & vocabulary)

    return score


def rows_for(
    repo: CorpusRepository,
    cited: tuple[int, ...],
    retrieved: tuple[int, ...],
    question: str = "",
) -> tuple[Row, ...]:
    """Cited entries first, then the rest by how close their wording is to the topic.

    Cited first because those are the ones the answer stands on, and a reader
    checking prose against a table should not have to hunt for them. The rest are
    ranked rather than left in retrieval order, which for a single search is the
    corpus's own identifier order and so carries no relevance at all -- it is what
    put a 490 um chromosome in the top five of a question about a 1 um cell.
    """
    ordered: list[int] = [b for b in cited if repo.get(b) is not None]
    seen = set(ordered)
    rest = []
    for bnid in retrieved:
        if bnid not in seen and repo.get(bnid) is not None:
            rest.append(bnid)
            seen.add(bnid)
    score = _relevance(repo, cited, question)
    # Stable, so entries the score cannot separate stay in the order they were met.
    rest.sort(key=lambda bnid: -score(bnid))
    ordered += rest

    out = []
    for bnid in ordered:
        found = repo.get(bnid)
        if found is None:  # pragma: no cover - filtered above
            continue
        entry = found.entry
        out.append(
            Row(
                bnid=entry.bnid,
                property=entry.property,
                organism=entry.organism,
                value=entry.value_display,
                units=entry.units,
                reference=entry.reference,
                cited=bnid in cited,
                method_recorded=bool(entry.measurement_method.strip()),
                retrieved=bnid in retrieved,
            )
        )
    return tuple(out)


def _cell_lines(text: str, width: int) -> list[str]:
    """Wrapped to at most two lines, the second truncated with an ellipsis.

    Truncating rather than wrapping further keeps every row the same height, which
    is what makes a long table scannable and what the reference page does.
    """
    wrapped = textwrap.wrap(text, width=width) or [""]
    lines = wrapped[:LINES_PER_ROW]
    if len(wrapped) > LINES_PER_ROW and width >= 2:
        lines[-1] = lines[-1][: width - 1].rstrip() + "…"
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


def _banner(width: int) -> str:
    """A dashed rule naming what follows, so the break is not read as the table ending."""
    label = f" {UNCITED_BANNER} "
    fill = max(0, width - len(label))
    left = fill // 2
    return "-" * left + label + "-" * (fill - left)


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
    rule = "  ".join("-" * width for _, _, width in COLUMNS)
    header = "  ".join(title.ljust(width) for _, title, width in COLUMNS).rstrip()
    out = [header, rule]
    for index, row in enumerate(shown):
        if index and shown[index - 1].cited and not row.cited:
            # A reader checking the prose needs the entries it rests on separated
            # from the ones it does not. The rest are still shown, because what the
            # corpus held and the answer passed over is part of the evidence.
            out.append(_banner(len(rule)))
        marks = row.markers()
        label = f"{marks} {row.property}" if marks else row.property
        cells = [
            _cell_lines(label if field == "property" else row.cell(field), width)
            for field, _, width in COLUMNS
        ]
        for line_number in range(LINES_PER_ROW):
            line = "  ".join(
                cells[i][line_number].ljust(width) for i, (_, _, width) in enumerate(COLUMNS)
            ).rstrip()
            if line:
                out.append(line)
    retrieved = total if total is not None else len(rows)
    if retrieved > len(shown) or matched > len(shown):
        out.append(summarise(len(shown), retrieved, matched, searches))
    if any(not row.retrieved for row in shown):
        out.append(NOT_RETRIEVED_LEGEND)
    if any(not row.method_recorded for row in shown):
        out.append(NO_METHOD_LEGEND)
    return "\n".join(out)
