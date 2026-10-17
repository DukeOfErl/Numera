## Context

The spec is Yoav's Claude Design canvas (read 2026-10-17). It has three artboards: the answer view
at 1650 px, the first view, and the citation pill with its key. Streamlit 1.61.1 is installed. The
widget choices follow the canvas session's own Streamlit mapping and the bundled
developing-with-streamlit references (`layouts.md`, `selection-widgets.md`), read 2026-10-17.

## Decisions

### D1. Entries are numbered through the session, by a pure function over the transcript

`entry_numbers(transcript)` walks the turns in order. For each turn it numbers:
1. the identifiers the answer cites, in the order they first appear in the text;
2. then the turn's evidence rows, cited first, then uncited.

An entry is numbered the first time it is seen. Because the result is a function of what is already
on the page, a rerun, the live path and the replay path all number alike, and no counter has to be
kept in step. Its scope is the browser session's transcript: a reload restarts the transcript, and
the numbering with it, exactly as it restarts the page.

An identifier the corpus does not hold gets no number and stays as written: a pill would claim a
row the list cannot show. The item already carries a warning saying the citation is unknown.

### D2. The pill is our own HTML, after escaping, in the one function that turns HTML on

`answer_markdown` keeps its rule: escape first, then insert our own markup. The superscript becomes
`<span class="sn-pill" title="…id…">n ★★★☆☆ sim ⚠️</span>`. The stars come from `trust_marks`, as
before, so nothing about who draws a tier changes (ADR-1630). The pill's CSS is page-level and
emitted once, as the feedback colour is. Colours use `currentColor` with opacity, so the pill
follows the reader's theme.

### D3. The evidence list is an HTML table, not a dataframe

A dataframe cannot wrap. The store's property names run to 36 words (median 14), so a dataframe
either truncates them or scrolls sideways; the canvas chose HTML for this reason.
- Each cell is escaped.
- The value cell is `white-space: nowrap`, so a number is never broken across lines
  (`grounded-answering`).
- There are no fixed pixel widths, so `COLUMN_WIDTHS` and the width-budget test go: there is no
  longer a horizontal scrollbar to protect the ID from.

Alternative rejected: `st.dataframe(on_select=…)` with clickable rows. It gives row selection but
loses wrapping.

### D4. An entry is opened with numbered pills, or a dropdown above twelve

The selector is `st.pills` with `selection_mode="single"`, defaulting to the first cited entry.
- **Above twelve entries** it becomes `st.selectbox`, with options like "7 · Average filament
  length". Above that point the pills become a wall of numbers (Yoav's call, 2026-10-17).
- **Keys** come from the question id, like the rating's.
- **The live path reserves a seat** and fills it after the agent's generator is spent, for the
  rating's reason (`answer`'s docstring). A widget drawn mid-answer is live, and a click would
  abandon the tool call.
- **Older turns are disabled while a question is answering**, for the same reason.

The record is drawn in `st.container(border=True)`. Objections are drawn as one `st.warning`
listing each reviewer's role and words, and are shown to the reader only, as before. The Trust
cell carries stars alone again.

### D5. The finished retrieval box is the search line

The canvas collapses the search into a caption. We keep `st.status`, collapsed, and change its label
to "Searched “…”, “…” · N retrieved, M cited", so the per-call progress stays openable. The search
terms come from a new field on the progress item, set from the retrieval's arguments.

### D6. `sim` replaces `#`, in both drivers

`#` collides with the "#1–#4" labels that papers use for rings, cells and samples. The pill's order
is the canvas's: number, stars, `sim`, ⚠. The terminal draws `★★★☆☆ sim ⚠️`.

### D7. First author and year, under the property

- **Harvested entries:** taken from the paper's CSL-JSON record. One author gives "Kamasaki 2007",
  two "Wu & Pollard 2005", three or more "Dhar et al. 2026".
- **Curated entries:** read from BioNumbers' reference string ("Wu JQ, Pollard TD. … 2005 …").
  The rule accepts only author lists of the form "Surname INITIALS" and a four-digit year. Anything
  else gives no short form, and the organism stands alone.

That is a classifier, so both directions were measured over the 423 curated references before it
was used (tasks 5.x). A wrong year mis-dates a paper while looking right; a missing short form costs
one grey word. The rule therefore leans towards giving none.

### D8. Chrome

- `initial_sidebar_state="collapsed"`.
- **In the sidebar:** the account and sign-out, the session budget, the data credit, and the trail
  under a "Dev" heading for roles granted it. Without the entries there is one view, so no tab
  strip.
- **Header:** the title, a subtitle naming the data ("BioNumbers + values harvested from papers"
  for the store), and the prototype line in amber. The pinned banner goes; the canvas puts the line
  in the header.
- **Under the question box:** the records note and who is signed in, via `st.bottom`.

### D9. First view

When the transcript is empty, the left column shows:
- a heading;
- one paragraph;
- three example questions as buttons. A click records the question under its own key, and the
  script treats it exactly as a submitted question; `question_pending` reads that key too.

The right column shows a bordered placeholder saying what will appear there.

## Risks / trade-offs

- **The HTML table is ours to keep accessible.** It uses real `<table>`, `<th>` and `<td>`
  elements, and escaped text only.
- **Numbers depend on the browser session's transcript.** After a reload, numbers restart while the
  conversation continues in the checkpoint. That is the same scope as the page's history, and the
  identifiers stay on hover and in the list.
- **The door's demo keeps ADR-1240's superscripts** until a later change. The door then shows a
  citation style the app no longer uses, flagged on the roadmap.
