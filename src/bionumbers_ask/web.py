"""Web driver: the second adapter over the same agent.

Streamlit re-runs its whole script on every interaction, so a driver built on it
has nowhere to keep anything between one question and the next except session
state. That suits the port rather than straining it: the conversation, the
accumulated spend and the ceiling in force all live in the checkpoint, and the
only thing this driver keeps is the session identifier that reaches them --
alongside a transcript of what has already been drawn, which is output rather
than state, and which the agent survives losing.

Events become items here, and the page draws from the items. The indirection
earns its place twice over. Streamlit composes successive writes to one screen
location into the last of them, so anything rendered in place and then
overwritten is unobservable afterwards -- to a reader scrolling back and to a
test alike; items are ordinary Python and can be asserted on directly. And the
agent's stream can be drained once, by a caller that is not drawing anything,
which is what lets the same events be rendered twice: now, and again on the
re-run after the next question.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterable, Iterator, MutableMapping
from contextlib import nullcontext
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import streamlit as st

from . import entries_table, messages, trace
from .agent import AskAgent
from .citations import format_citation
from .config import Config
from .corpus import load
from .events import Answer, AnswerEntries, Event, QuestionEnded, Retrieval
from .repository import CorpusRepository

# Namespaced, because session state is one flat dictionary shared with every
# widget key on the page: an unprefixed "session_id" is one careless `key=` away
# from being overwritten by a text input.
# One line on screen, which is the constraint: a banner that wraps becomes a block a
# reader learns to skip. Specific on both counts a vaguer line would lose --
# *not trustworthy* rather than merely unpolished, and *the original source* rather
# than "the cited entry", which reads as this page's own rendering of it and is the
# one thing checking it cannot verify. The README makes the same claim; if one
# changes, change both.
PROTOTYPE_NOTE = (
    "**Prototype — not scientifically trustworthy.** "
    "Verify every number against the original source."
)
PROTOTYPE_SHORT = "Prototype — verify numbers against the original source."

# Pinned to the viewport rather than written into the page. Drawn as an ordinary
# element it sat above the conversation and scrolled away with the first answer --
# so the reader who has read several answers, and is therefore most likely to have
# started trusting them, is the one who can no longer see it.
#
# Fixed under Streamlit's own header, with the main container padded so nothing
# hides behind it. The two test ids are Streamlit's stable ones (verified against
# 1.61.1); if a future version renames them the banner degrades to sitting at the
# top of the page, which is where it was before -- it cannot vanish.
PROTOTYPE_BANNER_CSS = """
<style>
[data-testid="stMainBlockContainer"] { padding-top: 4.5rem; }
.bn-caveat {
  position: fixed; top: 3.5rem; left: 0; right: 0; z-index: 999;
  padding: 0.45rem 1rem; text-align: center; font-size: 0.85rem; line-height: 1.3;
  background: #7a4a00; color: #ffe9c2;
  border-bottom: 1px solid rgba(255, 233, 194, 0.35);
}
@media (prefers-color-scheme: light) {
  .bn-caveat { background: #ffecb3; color: #4a3000; }
}
</style>
"""

SESSION_KEY = "bionumbers_ask.session"
TRANSCRIPT_KEY = "bionumbers_ask.transcript"

# The session identifier lives in the URL as well as in session state. Session
# state dies with the server; the checkpoint it points at does not, so without
# this a restart would orphan every conversation on disk and start a new one.
QUERY_KEY = "session"

DEFAULT_CHECKPOINTS = "checkpoints/ask.sqlite"

# Rows in the table beside the answer, against the terminal's five. Small on
# purpose: this is the evidence a reader checks the prose against, and a table
# long enough to scroll is one nobody reads. Nothing is hidden -- every retrieved
# entry is in the side panel, whole and openable.
# Two caps, not one. A single cap on the table spent all of its rows on cited
# entries whenever an answer cited many -- nine cited entries against eight rows
# dropped one of them and took the uncited section with it. The cited entries are
# what the prose stands on and a reader checking it needs every one; the uncited
# are context, and four of them is enough to show the answer had alternatives.
CITED_ROWS = 10
UNCITED_ROWS = 4

# Pixel widths in the terminal table's proportions (29:17:13:12:7:18), scaled so
# the table fits the main column without a horizontal scrollbar. Sized to the
# column rather than to the content on purpose: a table you have to scroll
# sideways hides the identifier, which is the one cell a reader is checking. A
# truncated cell opens in full on a double click, so nothing is lost.
COLUMN_WIDTHS = {
    "Property": 190,
    "Organism": 115,
    "Value": 85,
    "Units": 70,
    "ID": 60,
    "Reference": 120,
}


class Kind(StrEnum):
    """What an item is, so the page can choose how to draw it.

    The driver decides what kind of thing an event is; the page decides what that
    kind looks like. Keeping those apart is what makes the decision testable
    without a browser, since the second half is the part no test can see.
    """

    PROGRESS = "progress"
    WARNING = "warning"
    ANSWER = "answer"
    ENTRIES = "entries"
    ENDING = "ending"


@dataclass(frozen=True)
class Table:
    """The entries an answer is presented with, already selected and ordered.

    Carried on the item rather than looked up when drawn, so a re-run can redraw a
    past answer's table without the repository and without re-running its search.
    """

    rows: tuple[entries_table.Row, ...] = ()
    retrieved: int = 0
    matched: int = 0
    searches: int = 0


@dataclass(frozen=True)
class Item:
    kind: Kind
    text: str = ""
    table: Table | None = None
    # Decided here rather than at the screen, for the reason the whole module is
    # shaped this way (ADR-0100): whether the run is over is a decision, and a
    # test can read it off an item where it cannot read it off a drawn page.
    ends_the_run: bool = False
    run_spend: int = 0
    run_budget: int = 0


def item_for(event: Event, repo: CorpusRepository | None = None) -> Item | None:
    """One item for an event, or None for one the page does not draw.

    Every event the agent emits produces an item, warnings included: a warning that
    reaches this function and falls through is a fact the agent established and the
    page never said, which is worse than an ugly one.
    """
    if isinstance(event, Retrieval):
        return Item(Kind.PROGRESS, messages.retrieval_text(event))
    if isinstance(event, AnswerEntries):
        # Needs the corpus: the event carries identifiers, and the reference
        # deliberately never travels through the agent.
        if repo is None:
            return None
        rows = entries_table.rows_for(repo, event.cited, event.retrieved, event.question)
        if not rows:
            return None
        return Item(
            Kind.ENTRIES,
            table=Table(rows, len(event.retrieved), event.matched, event.searches),
        )
    warning = messages.warning_text(event)
    if warning is not None:
        return Item(Kind.WARNING, warning)
    if isinstance(event, Answer):
        return Item(Kind.ANSWER, event.text)
    if isinstance(event, QuestionEnded):
        return Item(
            Kind.ENDING,
            messages.ending_text(event),
            ends_the_run=event.reason in messages.STOP_THE_RUN,
            run_spend=event.run_spend,
            run_budget=event.run_budget,
        )
    return None


def items_for(events: Iterable[Event], repo: CorpusRepository | None = None) -> Iterator[Item]:
    """Each event's item, as the event arrives.

    A generator, because a question's events arrive over its whole life -- a
    search finishes long before the answer exists -- and draining before drawing
    would leave the page blank for all of it. The caller must drain: stopping
    part way leaves the question half-asked, with the model paid for and the
    checkpoint not written.
    """
    return (item for item in (item_for(event, repo) for event in events) if item is not None)


def session_id(
    state: MutableMapping[str, Any], params: MutableMapping[str, Any] | None = None
) -> str:
    """The session this browser tab is continuing, created on first use.

    Held in two places, because neither survives what the other does. Session
    state is per-tab and keeps two browsers apart, but dies when the server does.
    The URL survives a restart and a reload, and is what makes a session something
    a person can bookmark or hand to someone else -- but it is shared by anyone
    given the link, so it is where the identifier is *recovered*, never where it
    is decided.

    Takes both mappings rather than reaching for `st.session_state` and
    `st.query_params`, so a test can hold two of either.
    """
    params = {} if params is None else params
    if SESSION_KEY not in state:
        # Same width as the terminal driver's, so a session started in one can be
        # continued in the other by copying it.
        state[SESSION_KEY] = params.get(QUERY_KEY) or uuid.uuid4().hex[:8]
    params[QUERY_KEY] = state[SESSION_KEY]
    return state[SESSION_KEY]


def transcript(state: MutableMapping[str, Any]) -> list[tuple[str, list[Item]]]:
    """What has already been drawn, so a re-run can put it back on screen.

    Output, not state: the conversation itself is in the checkpoint, so losing
    this loses the page's history and not the agent's. A reload shows an empty
    page continuing a session that still remembers everything.
    """
    if TRANSCRIPT_KEY not in state:
        state[TRANSCRIPT_KEY] = []
    return state[TRANSCRIPT_KEY]


@st.cache_resource(show_spinner="Loading the corpus…")
def resources() -> tuple[CorpusRepository, AskAgent]:
    """The corpus index and the agent, built once for the life of the server.

    Cached because the indexes are built over the whole corpus and Streamlit
    would otherwise rebuild them on every interaction; task 8.2 verifies that
    they are not. Configuration comes from the environment because a Streamlit
    script has no argv to read it from.
    """
    trace.to_file(os.environ.get("BIONUMBERS_ASK_TRACE", trace.DEFAULT_FILE))
    repo = CorpusRepository(load(os.environ.get("BIONUMBERS_ASK_CORPUS", "")))
    checkpoints = os.environ.get("BIONUMBERS_ASK_CHECKPOINTS", DEFAULT_CHECKPOINTS)
    # The store is created on demand by the checkpointer, but its directory is not.
    directory = os.path.dirname(checkpoints)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return repo, AskAgent(repo, Config.from_env(), checkpoints)


def as_text(text: str) -> str:
    """Escape what Streamlit's markdown would read as something other than text.

    `$` opens inline mathematics. An ending line carries two of them -- "$0.008181
    (run $0.008181)" -- so the cost between was typeset as an equation and both
    signs were consumed as delimiters, leaving a figure with no currency on it.

    Applied at the point of drawing rather than where the text is built: the item
    carries what the ending says, and how to stop a renderer misreading it is the
    renderer's problem. The terminal driver prints the same string and needs none
    of this.
    """
    return text.replace("$", r"\$")


def _row_label(row: entries_table.Row) -> str:
    """One line identifying an entry, for the side panel's collapsed rows."""
    value = "" if not row.has_scalar else f"{row.value} {row.units}".strip()
    parts = [row.property, row.organism, value, format_citation(row.bnid)]
    label = " · ".join(part for part in parts if part)
    marks = _markers(row)
    return f"{marks} {label}" if marks else label


def _markers(row: entries_table.Row) -> str:
    """The terminal's markers, plus the one only this driver needs.

    The value column here is blank where the corpus holds no scalar, so the
    absence is marked and explained once in the legend rather than spelled out in
    every such row.
    """
    marks = row.markers()
    return marks + (entries_table.NO_SCALAR if not row.has_scalar else "")


def _legend(rows: tuple[entries_table.Row, ...]) -> list[str]:
    """What the markers mean, said before the table rather than after it.

    A legend below the table is read after the rows it explains, which is the
    wrong order: a reader meets a dagger, wonders, and has to look past the thing
    they were reading.
    """
    applying = (
        (entries_table.NOT_RETRIEVED_LEGEND, lambda r: not r.retrieved),
        (entries_table.NO_METHOD_LEGEND, lambda r: not r.method_recorded),
        (entries_table.NO_SCALAR_LEGEND, lambda r: not r.has_scalar),
        (entries_table.QUALIFIED_LEGEND, lambda r: r.qualified),
        (entries_table.FUSED_LEGEND, lambda r: r.fused),
        (entries_table.IMPLAUSIBLE_LEGEND, lambda r: r.implausible_span),
    )
    return [legend for legend, applies in applying if any(applies(row) for row in rows)]


def _frame(rows: tuple[entries_table.Row, ...]) -> list[dict[str, Any]]:
    """The table's cells, in the reference database's column order."""
    return [
        {
            "Property": f"{_markers(row)} {row.property}".strip(),
            "Organism": row.organism,
            "Value": row.value if row.has_scalar else "",
            "Units": row.units,
            # A string, not a number: an identifier formatted as a quantity picks
            # up a thousands separator and stops matching the citation in the prose.
            "ID": str(row.bnid),
            "Reference": row.reference,
        }
        for row in rows
    ]


def _draw_entry(row: entries_table.Row) -> None:
    """The whole entry, behind the row that names it.

    Every field is read from the corpus. Nothing here came from the model, so an
    opened row is the evidence against which its prose can be checked -- which is
    the point of being able to open it at all.
    """
    st.markdown(f"**{as_text(row.property)}** — {as_text(row.organism)}")
    if row.has_scalar:
        st.markdown(f"{as_text(row.value)} {as_text(row.units)}".strip())
    else:
        st.caption(entries_table.NO_SCALAR_LEGEND)
    if row.method:
        st.markdown(f"*Measurement method.* {as_text(row.method)}")
    else:
        st.caption(entries_table.NO_METHOD_LEGEND)
    if row.comments:
        st.markdown(f"*Comments.* {as_text(row.comments)}")
    keywords = shown_keywords(row)
    if keywords:
        st.caption("Keywords: " + as_text(", ".join(keywords)))
    reference = row.reference or "(no reference recorded)"
    pubmed = f" · PubMed {row.reference_pubmed_id}" if row.reference_pubmed_id else ""
    st.caption(as_text(f"{reference}{pubmed}"))


def shown_keywords(row: entries_table.Row) -> list[str]:
    """The keywords that will actually appear, markup already stripped.

    Testing `row.keywords` instead drew a bare "Keywords: " for every entry whose
    only keyword was the injected `<IMG SRC=...>` -- which `_without_markup`
    empties, and which the corpus carries on 10,206 of 14,294 records.
    """
    return [keyword for keyword in row.keywords if keyword]


def summary_for(table: Table, shown: int) -> str:
    """How much went unshown, or "" when there is nothing to report.

    Guarded as the terminal guards it. `table.rows` includes entries cited without
    being retrieved while `table.retrieved` counts only retrieved ones, so `shown`
    can exceed it and the ungated sentence read "showing 4 of 1 entries retrieved".
    """
    if table.retrieved > shown or table.matched > shown:
        return entries_table.summarise(shown, table.retrieved, table.matched, table.searches)
    return ""


def _dataframe(rows: tuple[entries_table.Row, ...]) -> None:
    st.dataframe(
        _frame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            name: st.column_config.TextColumn(width=width) for name, width in COLUMN_WIDTHS.items()
        },
    )


def _draw_table(table: Table) -> None:
    """The entries table: cited first, separated from the rest.

    Two tables under two headings rather than one with a marker column. The
    separation is what a reader checking prose against evidence needs, and a
    column they have to scan for does not give it to them.
    """
    every_cited = tuple(row for row in table.rows if row.cited)
    cited = every_cited[:CITED_ROWS]
    rest = tuple(row for row in table.rows if not row.cited)[:UNCITED_ROWS]
    shown = cited + rest

    if cited:
        st.markdown("**Cited in the answer**")
        _dataframe(cited)
    else:
        # Not silence: an answer that cited nothing is a fact about the answer,
        # and a table that just began with uncited rows read as though it had.
        st.markdown(f"**{entries_table.NOTHING_CITED}**")
    # Loud, not a caption. An answer resting on an entry the table does not show
    # is the one omission a reader cannot detect by looking, and the table is
    # where they would look. All of them are in the side panel.
    missing = len(every_cited) - len(cited)
    if missing:
        st.warning(
            as_text(
                f"{missing} more cited "
                f"{'entry is' if missing == 1 else 'entries are'} not shown here — "
                "every one is in the side panel."
            ),
            icon=":material/warning:",
        )
    # Between the two tables: a reader meets the marks in the cited rows, reads
    # what they mean, and carries that into the rows below. Before both it is
    # explaining marks nobody has seen yet; after both it is too late.
    for line in _legend(shown):
        st.caption(as_text(line))
    if rest:
        st.markdown(f"**{entries_table.UNCITED_BANNER.capitalize()}**")
        _dataframe(rest)

    note = entries_table.dimension_note(table.rows)
    if note:
        st.caption(as_text(note))
    summary = summary_for(table, len(shown))
    if summary:
        # Body text, not a caption. How much of the corpus went unlooked-at is one
        # of the few things a reader can use to judge whether an answer is worth
        # trusting, and it was set in the same grey as the footnotes.
        st.markdown(as_text(summary.removeprefix("… ")))


def draw_full_entries(table: Table | None) -> None:
    """Every retrieved entry, whole and openable, in the side panel.

    Drawn whether or not there is anything to put in it, so the panel is part of
    the page rather than something that appears once a question has been asked --
    a panel that materialises later reads as a glitch, and other sections will
    live beside this one.

    All of the entries, not the table's first few: this is where "the rest" is
    reached, and an entry the answer passed over is part of the evidence. Only
    the newest question's, because the panel is for reading the answer in front
    of you and a session's worth would bury it.
    """
    with st.sidebar:
        st.header("Full entries")
        if table is None:
            st.caption("The entries behind an answer appear here once you ask something.")
            return
        for row in table.rows:
            with st.expander(as_text(_row_label(row))):
                _draw_entry(row)


def latest_table(transcript: Iterable[tuple[str, list[Item]]]) -> Table | None:
    """The newest question's entries, or None if that question produced none.

    The newest question's, not the newest that had any. Falling back to an older
    one leaves a previous question's entries under a heading that says "Full
    entries", with nothing on the page marking them as belonging to a question
    already answered -- and the main column's warning about rows not shown here
    would then be pointing at a panel that no longer holds them.
    """
    for _, items in reversed(list(transcript)):
        for item in items:
            if item.kind is Kind.ENTRIES and item.table is not None:
                return item.table
        return None
    return None


def draw_prototype_banner() -> None:
    """The caveat, pinned so it is still there after the tenth answer.

    Deliberately not a dismissible one. The page shows identifiers, dimension
    checks and marked entries -- every signal a reader uses to judge a number
    solid -- so the statement that none of it has been evaluated has to outlast
    the reader's growing confidence in it.
    """
    st.markdown(PROTOTYPE_BANNER_CSS, unsafe_allow_html=True)
    # The note is written as markdown, and this element is raw HTML, where `**`
    # renders as two asterisks. One source of words, two renderings of it.
    emphasised = PROTOTYPE_NOTE.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
    st.markdown(f'<div class="bn-caveat">{emphasised}</div>', unsafe_allow_html=True)


def run_is_over(transcript: Iterable[tuple[str, list[Item]]]) -> bool:
    """Whether any question ended the run, so the page should stop taking them.

    The terminal returns from its read loop on these endings; without the same
    check here the chat input stays live and every further question replays an
    identical refusal, which reads as a broken app rather than a limit reached.
    Any question, not the last: nothing un-spends a run budget.
    """
    return any(
        item.ends_the_run for _, items in transcript for item in items if item.kind is Kind.ENDING
    )


def run_status(
    transcript: Iterable[tuple[str, list[Item]]],
    fallback: tuple[int, int] | None = None,
) -> tuple[int, int] | None:
    """What the run has spent and what it may spend.

    Read from the ending events where there is one, rather than from configuration,
    because a session resumed in a process configured differently spends against
    the budget it was created with -- reading the environment would report a cap
    this run is not subject to.

    `fallback` covers the interval before the first answer, where no ending exists
    to read. It is the run's own recorded spend against the configured budget,
    which is the same pair the first ending will carry. Without it the panel gained
    a section the moment a question completed, and a layout that grows under the
    reader is a worse surprise than a bar reading zero.
    """
    latest = fallback
    for _, items in transcript:
        for item in items:
            if item.kind is Kind.ENDING and item.run_budget:
                latest = (item.run_spend, item.run_budget)
    return latest


def draw(item: Item) -> None:
    """Draw one item. The only function here that touches the screen."""
    if item.kind is Kind.ANSWER:
        st.markdown(as_text(item.text))
    elif item.kind is Kind.ENTRIES:
        if item.table is not None:
            _draw_table(item.table)
    elif item.kind is Kind.WARNING:
        st.warning(as_text(item.text), icon=":material/warning:")
    elif item.kind is Kind.PROGRESS:
        st.caption(f"· {as_text(item.text)}")
    else:
        st.caption(as_text(item.text))


def _retrieval_box(expanded: bool, state: str = "running"):
    return st.status("Searching the corpus…", expanded=expanded, state=state)


def answer(
    events: Iterable[Event],
    repo: CorpusRepository | None = None,
    into: list[Item] | None = None,
) -> list[Item]:
    """Draw a question's items as they arrive, recording each into `into` as it goes.

    Each progress line is its own element rather than one line rewritten in
    place. Streamlit composes successive writes to one screen location into the
    last of them, so a rewritten line would leave no trace of the sequence -- for
    a reader scrolling back or for a test (ADR-0100).

    `into` is the transcript's own list, filled in place, so a failure while
    drawing cannot lose the question. Returning the items and letting the caller
    append them meant a raising `draw` skipped the append entirely, while the agent
    had already persisted the turn -- the page forgot a question the model
    remembered, and the next answer was built on context nothing on screen showed.
    """
    box = _retrieval_box(expanded=True)
    drawn: list[Item] = [] if into is None else into
    for item in items_for(events, repo):
        with box if item.kind is Kind.PROGRESS else nullcontext():
            draw(item)
        drawn.append(item)
    box.update(label="Retrieval", state="complete", expanded=False)
    return drawn


def show(items: Iterable[Item]) -> None:
    """Put a finished question's items back on screen after a re-run.

    Retrieval is collapsed here, where the live path leaves it open: while a
    question is running the progress is the only thing to look at, and once it
    has an answer the progress is the thing in the way.
    """
    items = list(items)
    progress = [item for item in items if item.kind is Kind.PROGRESS]
    if progress:
        with _retrieval_box(expanded=False, state="complete"):
            for item in progress:
                draw(item)
    for item in items:
        if item.kind is not Kind.PROGRESS:
            draw(item)
