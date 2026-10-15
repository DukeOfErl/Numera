"""What one review screen shows, decided outside the browser.

`review_app.py` is a script Streamlit re-runs from the top on every click, so everything it decides
that is not a screen element lives here and is asserted without a browser (design D9). This module
and that script are the only two in the package allowed to reach `scinumbers_ask`;
`tests/test_bionumbers_dependency_direction.py` is where that stops being a convention.

Two things the reviewer must never learn shape most of what follows. The order of the two texts is
drawn from the item id rather than from which of them supports the value, and **nothing here reads
`second_kind` or `distractor_type`** (design D5): an item whose second text is a legitimate second
occurrence has to look exactly like one whose second text is a distractor, or else the shape of the
screen answers the question being asked. The decisions this collects measure the extractor, so
anything that tells the reviewer what to say makes the measurement of itself.

The reviewer is the check the mechanical checks cannot be -- the quote checker passes a sentence
that mentions the number without asserting it, and only a person sees that -- which is why the
condition block lists fields the paper never stated and why the citation carries every identifier:
both are material for a judgement, not decoration.
"""

from __future__ import annotations

import hashlib
import html
import os
from dataclasses import dataclass

from sqlalchemy import Engine

from bionumbers import store
from bionumbers.records import (
    CONDITION_FIELDS,
    Claim,
    Location,
    Paper,
    Provenance,
    ReviewItem,
    TableView,
)
from scinumbers_ask import web

DB_URL_ENV = "BIONUMBERS_REVIEW_DB_URL"

TITLE = "SciNumbers review"

#: The two verdicts, as the reviewer reads them. They are the radio's options and the values
#: `decision_from` maps, so the wording and the meaning cannot drift apart.
APPROVE = "Approve"
DISAPPROVE = "Disapprove"

#: Said when an item is saved without one half of the answer. Each names the missing half rather
#: than "the form is incomplete": the reviewer is one click from done and has to be told which
#: click. The choice comes first because it is the one a reviewer skips -- the verdict feels like
#: the question and the choice feels like a preamble, and the spec's own scenario is a verdict with
#: no choice.
CHOICE_REQUIRED = "Choose which text better fits the value before saving."
VERDICT_REQUIRED = "Say whether you approve or disapprove before saving."

#: The failed write (ADR-0930). It says the item is still open, because the reviewer's natural
#: reading of a page that did not move on is that their click missed -- and a reviewer who believes
#: a decision was taken when it was not is how the one thing this task collects goes missing
#: quietly.
NOT_SAVED = (
    "That decision was not saved, so this item is still open. Try again; if it fails a second "
    "time, stop and tell whoever runs this rather than reviewing on."
)

NOTHING_LEFT = "There is nothing left for you to review."

#: Each provenance state as a reviewer reads it. Prose rather than the state's name: the reviewer
#: is judging whether the value came from this paper under these conditions, and "FROM_METHODS" is
#: a token of ours while "from Methods" is a fact about the paper. `SUPPLEMENTARY_ONLY` says "not
#: read" out loud, because that field is the one place this prototype's reach (ADR-0050) shows up
#: on the screen, and a reviewer must not read a blank there as "the paper does not say".
PROVENANCE_LABELS: dict[Provenance, str] = {
    Provenance.BESIDE_VALUE: "beside the value",
    Provenance.FROM_METHODS: "from Methods",
    Provenance.BY_REFERENCE: "by reference to another paper",
    Provenance.SUPPLEMENTARY_ONLY: "in supplementary material only (not read)",
    Provenance.NOT_STATED: "not stated",
}

#: Shown where a field has no quote. An em dash rather than an empty cell: a blank reads as a
#: column that failed to fill, and this one is a fact about the paper.
_NO_QUOTE = "—"

#: The markdown characters that would eat part of a paper's sentence. `[` and `]` are the reason
#: this exists: the JATS reader keeps bibliographic markers as `[ref 27]` tokens because their
#: presence beside a number is what separates a measured value from a cited one (design D2), and
#: markdown reads `[...]` as the opening of a link. `*` and `_` become emphasis, a backtick opens
#: code, and `$` opens mathematics in Streamlit's renderer.
_MARKDOWN = str.maketrans({character: "\\" + character for character in "[]*_`$"})


@dataclass(frozen=True)
class Shown:
    """One of the two texts, as it appears on the screen.

    `is_supporting` is for the record, never for the page: it is what `decision_from` turns the
    reviewer's "A" into. No field here carries the second text's kind or type, which is the
    structural half of "the kind is never shown".
    """

    label: str
    """"A" or "B"."""
    text: str
    location_line: str
    is_supporting: bool
    passage_id: str = ""
    """Where the text sits, so the table beneath can mark its cell with this label."""


@dataclass(frozen=True)
class Decision:
    """A complete answer for one item: both halves and whatever the reviewer wrote."""

    chosen_label: str
    chosen_supporting: bool
    approved: bool
    comment: str


class Incomplete(Exception):
    """One half of the answer is missing. The page says `message` and keeps the item open.

    Carries the sentence rather than a code the page would have to map: there is one caller and
    two cases, and a mapping in the driver is a second place for the wording to be wrong.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def texts_in_order(item: ReviewItem) -> tuple[Shown, Shown]:
    """The two texts as A and B, in an order that carries no information about which is which.

    Derived from the item id, and deliberately not from a random draw: a Streamlit script re-runs
    from the top on every interaction, so a coin flipped here would land differently on the rerun
    that follows the reviewer's click -- they would answer about one arrangement and be recorded
    against another, and every such decision would be wrong in the record while looking ordinary.
    A hash of the id is fixed for the life of the item and unpredictable across items, which is
    what "stable but uninformative" needs.

    Not the id's own first character: item ids are generated, and a scheme that numbers them within
    a paper would put every first item the same way round.
    """
    supporting_first = (hashlib.sha256(item.item_id.encode()).digest()[0] & 0x80) == 0
    first_quote, first_supports = (
        (item.supporting, True) if supporting_first else (item.second, False)
    )
    second_quote, second_supports = (
        (item.second, False) if supporting_first else (item.supporting, True)
    )
    return (
        Shown(
            label="A",
            text=first_quote.text,
            location_line=location_line(first_quote.location),
            is_supporting=first_supports,
            passage_id=first_quote.location.passage_id,
        ),
        Shown(
            label="B",
            text=second_quote.text,
            location_line=location_line(second_quote.location),
            is_supporting=second_supports,
            passage_id=second_quote.location.passage_id,
        ),
    )


def as_markdown(text: str) -> str:
    """The paper's text as markdown that renders exactly the paper's characters.

    Escaping and nothing else. The value is deliberately *not* emphasised in the texts (ADR-0940,
    Yoav's decision of 2026-09-22): a text is shown as the paper wrote it, so nothing on the
    screen points at the number the reviewer is being asked to find, and a text that states the
    value looks no different from one that merely mentions a number near it. The bolding this
    replaced lit up every `1` in a value of `39 ± 1`, which was the review's finding 7 -- moot now.
    """
    return text.translate(_MARKDOWN)


#: The table beneath the texts, and the marks on the two cells. One style block per table
#: rather than one per page, because a Streamlit script has no head to put it in and a
#: repeated block costs nothing. Both marks look the same on purpose: which cell is A and which
#: is B is the only information they may carry.
_TABLE_STYLE = (
    "<style>"
    ".bn-table table{border-collapse:collapse;font-size:0.85em;margin:0.25em 0}"
    ".bn-table caption{caption-side:top;text-align:left;padding:0.25em 0}"
    ".bn-table th,.bn-table td{border:1px solid #bbb;padding:0.2em 0.5em;vertical-align:top}"
    ".bn-table th{font-weight:600;background:rgba(127,127,127,0.12)}"
    ".bn-table td.bn-mark{outline:2px solid #1f77b4;outline-offset:-2px}"
    ".bn-table .bn-badge{display:inline-block;margin-left:0.4em;padding:0 0.35em;"
    "border-radius:0.25em;font-size:0.8em;font-weight:700;color:#fff;background:#1f77b4}"
    ".bn-table .bn-foot{font-size:0.8em;margin:0.25em 0 0.5em}"
    "</style>"
)


def tables_html(item: ReviewItem) -> tuple[str, ...]:
    """Each table the item's texts sit in, as HTML for the page, with both cells marked.

    Whole and with its caption, because two header fragments do not orient anyone in a table
    with a spanning group header and a control column (Table 3 of PMC13118904 is the case that
    asked for this). The cells of A and B are marked alike, with their labels, and the value is
    not distinguished anywhere in the grid: the table orients the reviewer, it must not answer for
    them. Nothing here reads which text supports the value.
    """
    marks = {shown.passage_id: shown.label for shown in texts_in_order(item) if shown.passage_id}
    return tuple(table_html(table, marks) for table in item.tables)


def table_html(table: TableView, marks: dict[str, str]) -> str:
    """One table as the paper laid it out, cells named in `marks` carrying their label."""
    caption = " ".join(part for part in (table.label, table.caption) if part)
    parts = [_TABLE_STYLE, '<div class="bn-table"><table>']
    if caption:
        parts.append(f"<caption>{html.escape(caption)}</caption>")
    for row in table.rows:
        cells = []
        for cell in row:
            tag = "th" if cell.header else "td"
            attributes = ""
            if cell.colspan > 1:
                attributes += f' colspan="{cell.colspan}"'
            if cell.rowspan > 1:
                attributes += f' rowspan="{cell.rowspan}"'
            content = html.escape(cell.text)
            label = marks.get(cell.passage_id) if cell.passage_id else None
            if label is not None:
                attributes += ' class="bn-mark"'
                content += f'<span class="bn-badge">{html.escape(label)}</span>'
            cells.append(f"<{tag}{attributes}>{content}</{tag}>")
        parts.append("<tr>" + "".join(cells) + "</tr>")
    parts.append("</table>")
    if table.foot:
        parts.append(f'<p class="bn-foot">{html.escape(table.foot)}</p>')
    parts.append("</div>")
    return "".join(parts)


def location_line(location: Location) -> str:
    """Where in the paper a text sits, as one line.

    A table cell is its headers and the cell, never the table: the headers are what say which
    condition the number belongs to, and the rest of the table is a page of numbers the reviewer is
    not being asked about -- and among which the value under review would be one row of many.

    Falls back to the passage id where the reader recorded no section path. A text with no location
    at all reads as one nobody can find in the paper, which is worse than an identifier only we
    can resolve.
    """
    parts = [" > ".join(location.section_path) or location.passage_id]
    if location.row_headers:
        parts.append("row: " + ", ".join(location.row_headers))
    if location.column_headers:
        parts.append("column: " + ", ".join(location.column_headers))
    return " · ".join(parts)


def condition_rows(claim: Claim) -> list[tuple[str, str, str]]:
    """Every condition and method field, as (field, where it came from, quote).

    Every field, including the ones the paper never states. The reviewer is being asked whether the
    value came from this paper *under these conditions*, which they cannot judge from a block
    listing only what was found: an absent row and a row reading "not stated" are the same fact
    about the paper, and only one of them is visible.
    """
    stated = {field.name: field for field in claim.conditions}
    # A name the extractor produced that `CONDITION_FIELDS` does not know goes after the known
    # ones rather than being dropped. A condition on the screen that does not belong there costs a
    # comment; one that never reached the screen costs a judgement made without it.
    names = list(CONDITION_FIELDS) + [name for name in stated if name not in CONDITION_FIELDS]
    rows = []
    for name in names:
        field = stated.get(name)
        provenance = field.provenance if field else Provenance.NOT_STATED
        # `reference` where there is no quote: a `BY_REFERENCE` field whose cell is empty reads as
        # a bug beside a provenance that says the paper pointed somewhere.
        quote = (field.quote or field.reference) if field else ""
        rows.append((_field_label(name), PROVENANCE_LABELS[provenance], quote or _NO_QUOTE))
    return rows


def citation_line(paper: Paper) -> str:
    """The paper as one line: title, year, and every identifier the record carries.

    All three identifiers, because the reviewer's route to the paper itself is whichever one their
    library resolves, and a line built around one of them fails for whoever does not have that one.
    Empty parts are dropped rather than left blank: ` ·  · ` reads as data missing about the paper,
    where what it means is that the index never carried it.
    """
    year = f"({paper.year})" if paper.year else ""
    parts = [
        " ".join(part for part in (paper.title, year) if part),
        paper.pmcid,
        # Prefixed, because a bare number after a PMCID is unreadable as an identifier of its own.
        f"PMID {paper.pmid}" if paper.pmid else "",
        f"doi:{paper.doi}" if paper.doi else "",
    ]
    return " · ".join(part for part in parts if part)


def decision_from(
    item: ReviewItem, choice: str | None, verdict: str | None, comment: str
) -> Decision:
    """One reviewer's answer for one item, or `Incomplete` naming the half that is missing.

    The choice is checked first and independently of the verdict, which is the spec's own scenario:
    a reviewer who approves without choosing a text has not completed the item. Both are required
    every time -- the choice is made whether the second text is a distractor or a second occurrence
    (design D5), so being asked to choose says nothing about the item.

    The label is turned into `chosen_supporting` here rather than in the page, because the mapping
    is the one thing about the screen that the record has to preserve: the order came from
    `texts_in_order`, and a page that stored "A" would leave every decision uninterpretable the day
    the ordering changed.
    """
    if choice is None:
        raise Incomplete(CHOICE_REQUIRED)
    if verdict is None:
        raise Incomplete(VERDICT_REQUIRED)
    shown = {text.label: text for text in texts_in_order(item)}
    if choice not in shown:
        raise ValueError(f"no text is labelled {choice!r}")
    # Not `approved = verdict == APPROVE` on its own: that records an unrecognised string as a
    # disapproval, which is a judgement nobody gave and which nothing downstream could tell from
    # one that was.
    if verdict not in (APPROVE, DISAPPROVE):
        raise ValueError(f"not a verdict: {verdict!r}")
    return Decision(
        chosen_label=choice,
        chosen_supporting=shown[choice].is_supporting,
        approved=verdict == APPROVE,
        comment=comment,
    )


def store_engine() -> Engine | None:
    """The engine holding the review tables, or None where the deployment configures none.

    The same `[connections.usage]` section, and so the same database, as the trail and the accounts
    table: the review tables are three more tables in it, and a second secrets section would be a
    second thing to get wrong on a deployment whose first symptom is a page nobody can use.

    `web.trail_destination` is reused rather than a second `st.connection` call because it caches
    the engine at global scope across sessions -- a fresh engine per rerun would pay TCP, TLS and
    Postgres auth before every `next_item`, on a page that reruns on every click.

    Named here rather than called from the page so the page's own tests can hand it a database with
    no connection string, and so "which database" is one decision in one place.

    Where no `[connections.usage]` is configured, `BIONUMBERS_REVIEW_DB_URL` -- the variable
    `bionumbers load` reads -- names the store instead, so a run loaded into a local SQLite file can
    be reviewed on the machine that produced it. Secrets win when both are present: the deployed
    page must not be redirected by an environment variable.
    """
    configured = web.trail_destination()
    if configured is not None:
        return configured
    url = os.environ.get(DB_URL_ENV, "").strip()
    return store.engine_from_url(url) if url else None


def _field_label(name: str) -> str:
    """`growth_phase` as a reviewer reads it. The record's field names are the analysis's, not
    theirs."""
    return name.replace("_", " ").capitalize()
