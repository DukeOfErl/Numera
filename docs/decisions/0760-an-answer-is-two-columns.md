# ADR-0760: An answer is two columns, and the page is wide

- **Status:** accepted
- **Date:** 2026-09-15
- **Pull request:** `feat/answer-feedback`

## Context

An answer is prose plus the corpus entries it rests on, and until now both were
drawn down one centred column: prose, warning, rating, cited table, legend,
uncited table, dimension note, corpus summary. The reader checking a number in
the prose against the row it came from had to scroll between the two and hold the
number in their head while doing it — and that check is the whole point of a tool
whose own banner says to verify every figure against the original source.

Everything added to the turn made it worse, because everything was added below.
Three consecutive fixes in this change were all the same fix: move the thing up
so the reader does not have to scroll past the evidence to reach it. The rating
went from the bottom of the turn to the foot of the prose; the uncited rows went
behind a fold; the corpus summary had already been promoted from caption to body
text for the same reason. A layout where the recurring problem is "the useful
thing is below the table" is the wrong layout, not a sequence of placement bugs.

Options on the table:

- **Keep one column and keep promoting things above the table.** Cheapest, and
  each individual move is defensible. But the table is the thing that is long,
  and anything below it stays hard to reach — the fixes compete with each other
  for the space above.
- **Put the table in the sidebar.** The sidebar already holds every retrieved
  entry, whole and openable. Rejected: that panel is for digging, and the table
  in the main column is for checking. Merging them loses the distinction, and the
  sidebar is narrow enough that the table would scroll sideways.
- **Two columns within the turn, prose left and entries right.** What was chosen.

## Decision

Each answered turn draws into two columns — the prose, its warnings, its rating
and its ending on the left; the entries table, its legend and the corpus summary
on the right — and the page is `layout="wide"` to give them room.

`_column_for` decides which column an item goes to, by kind, in one place that
both the live path and the replay path call. They draw the same turn from two
different call sites, and a split computed twice is a split that drifts.

**The width split is `READING_SPLIT = (5, 6)`, and the larger share goes to the
evidence deliberately.** The entries table's column widths are fixed pixels
summing to 640; below roughly that the dataframe grows a horizontal scrollbar,
and the first column it takes away is the identifier — the one cell a reader is
checking. Prose tolerates a narrower measure; the table does not tolerate a
narrower width at all, it just starts hiding things. `layout="wide"` follows from
the same arithmetic: the centred layout's main area is about 700px, and no split
of 700 leaves 640 on one side.

## Trade-off accepted

**Streamlit columns do not stack until the viewport is narrow.** Between roughly
640px and the width this layout assumes, both columns are cramped rather than
stacked — so a small laptop, or a browser window taking half a screen, gets a
worse layout than the single column it replaces. This is accepted rather than
solved: the alpha readers are at desks, and the alternative is a media-query
fight with Streamlit's own grid. **If a reader reports a cramped page, this is
the first thing to look at**, and the fix is a narrower `READING_SPLIT` or a
single column below a breakpoint — not a narrower table.

**Two arguments made earlier in this change are now weaker, and both are recorded
where they were made rather than quietly left standing.** The rating's placement
at the foot of the prose was justified by keeping it above a table that could
push it off the screen; the table is beside it now, so the justification is the
plainer one that a reader forms a view at the end of the prose. Folding the
uncited rows was justified by their length in front of a reader checking the
prose; they no longer push anything down, and the argument survives only in the
weaker form that a page is as tall as its tallest column.

**A wide page is not free for the prose.** Long lines are harder to read, which is
why the prose takes the smaller share — but a reader on a very wide monitor gets a
wider measure than is comfortable, and nothing here caps it.
