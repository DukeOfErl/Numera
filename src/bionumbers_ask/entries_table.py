"""The entries table an answer is presented with.

Selection and ordering live here because every driver needs the same ones; the
rendering does not, because a terminal and a browser have nothing in common there.
The reference is looked up here rather than carried through the agent: it is
presentation, and at a median 183 characters it would more than double what a
50-row search costs if it reached the model.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class Row:
    bnid: int
    property: str
    organism: str
    value: str
    units: str
    reference: str
    cited: bool

    def cell(self, field: str) -> str:
        return str(getattr(self, field))


def rows_for(repo: CorpusRepository, cited: tuple[int, ...], retrieved: tuple[int, ...]) -> tuple[Row, ...]:
    """Cited entries first, then the rest in the order they were retrieved.

    Cited first because those are the ones the answer stands on, and a reader
    checking prose against a table should not have to hunt for them.
    """
    ordered: list[int] = [b for b in cited if repo.get(b) is not None]
    seen = set(ordered)
    for bnid in retrieved:
        if bnid not in seen and repo.get(bnid) is not None:
            ordered.append(bnid)
            seen.add(bnid)

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
    if searches:
        # Stated as a per-search sum rather than a union: beyond the row cap the
        # identities are unknown, so the entries two searches share cannot be
        # counted once. Naming the number of searches is what keeps that honest.
        across = f" across {searches} searches" if searches > 1 else ""
        parts.append(f"{matched} matched{across}")
    return "… " + "; ".join(parts)


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
    header = "  ".join(title.ljust(width) for _, title, width in COLUMNS).rstrip()
    out = [header, "  ".join("-" * width for _, _, width in COLUMNS)]
    for row in shown:
        cells = [_cell_lines(row.cell(field), width) for field, _, width in COLUMNS]
        for line_number in range(LINES_PER_ROW):
            line = "  ".join(
                cells[i][line_number].ljust(width) for i, (_, _, width) in enumerate(COLUMNS)
            ).rstrip()
            if line:
                out.append(line)
    retrieved = total if total is not None else len(rows)
    if retrieved > len(shown) or matched > len(shown):
        out.append(summarise(len(shown), retrieved, matched, searches))
    return "\n".join(out)
