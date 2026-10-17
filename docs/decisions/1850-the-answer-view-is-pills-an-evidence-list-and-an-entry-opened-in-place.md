# ADR-1850: The answer view is numbered pills, an evidence list, and an entry opened in place

- **Status:** accepted
- **Date:** 2026-10-17
- **Pull request:** not yet opened — branch `feat/answer-view-redesign` (`add-answer-view-redesign`)

## Context

The demo (2026-10-19, local) shows the ask agent answering from the harvest store, and the page
was built before the store existed. Each citation was a grey superscript identifier followed by
`#★★★☆☆⚠️` at text size (ADR-1240, ADR-1630). The entries were an `st.dataframe` with fixed pixel
columns, and the full entries sat in a sidebar tab.

Over the store this read badly:
- harvested labels such as `PMC2064542-5` are long;
- property names now run to 36 words (`harden-harvest`'s backfill, median 14), and the dataframe
  truncated them;
- the objection text was squeezed into a Trust cell that only a double click opened;
- `#` sat beside papers' own "rings #1–#4".

Yoav redesigned the view on a Claude Design canvas ("SciNumbers Ask redesign",
https://claude.ai/artifact/4H8KtYtaJaMns2kWyzpcAh). The canvas session also gave a Streamlit
mapping for it.

## Decision

The canvas is taken as the spec. Its sample content is illustrative and is replaced by what the
store holds.

- **Pills.** Each citation is drawn as one pill: the entry's number, its stars, `sim` and ⚠, with
  the identifier on hover.
  - Numbers come from `entry_numbers(transcript)`, a pure function over what is on the page. It
    numbers each answer's citations as they first appear, then that turn's other rows. The live
    path, the replay path and a rerun therefore agree, with no counter to keep in step.
  - A citation the corpus does not hold gets no number and stays as written.
  - Pills are drawn in `answer_markdown`, the one function that both escapes the text and turns
    HTML on.
- **Evidence list.** One HTML table per answer (`st.html`, not iframed, sanitised by Streamlit)
  with the columns #, Entry, Value, Trust and ID.
  - Entry holds the property, with "organism · first author year" in grey beneath it.
  - Value holds the value with its units, with the caveat marks after it. The value cell never
    breaks.
  - Uncited entries go under one collapsed row.
  - Without fixed widths the width budget and its test go: nothing scrolls sideways any more.
- **Open entry.** `st.pills` holds the numbers, and becomes `st.selectbox` above twelve entries
  (Yoav's call). The chosen entry opens in a bordered container in the evidence column.
  - The opened entry holds the full reference with DOI and PubMed links, and what each objecting
    reviewer said. The Trust cell goes back to stars alone.
  - On the live path the chooser is reserved where it belongs and filled once the generator is
    spent, for the rating's reason. On older turns it is disabled while a question is answering.
- **`sim` replaces `#`** in both drivers.
- **First author and year.** For harvested entries they come from the paper's CSL-JSON record
  (ADR-1640). For curated entries they come from BioNumbers' reference string, accepting only
  "Surname INITIALS" lists. Measured over the store's 330 distinct curated references, 270 get a
  label and 60 get none. Widening the rule for particles, "Jr" and "X et al." gained 22 labels,
  all correct on reading, and lost or changed none. Where a reference holds several years, the
  first year after the authors was the publication year in all seven cases. The cheap direction is
  none: a missing label costs a grey word, a wrong year mis-dates a paper while looking right.
- **Chrome.**
  - The sidebar starts collapsed. It holds the account, the budget, the data credit and, for
    roles granted it, the trail under a "Dev" heading: one view, so no tab strip.
  - The header carries the title, a subtitle naming the data, and the prototype line in amber; it
    was pinned to the viewport before.
  - Under the question box is one line: what is kept, whose money a question spends, and whose
    account it is. That line is visible on every screen, which the sidebar no longer is.
  - The finished retrieval box is labelled "Searched “…” · N retrieved, M cited".
  - The first view shows a heading, a paragraph and three example questions that ask themselves.

## Trade-off accepted

- **Numbers live in the browser session.** After a reload they restart while the conversation
  continues in the checkpoint. The identifiers stay on hover, in the list and in the record.
- **The HTML table is ours to keep accessible and escaped**, where a dataframe was Streamlit's.
- **The terminal keeps `[[id]]` and its own table.** Only `sim` changes there.
- **The sign-in door's demo keeps ADR-1240's superscripts** until a later change, so for now the
  door shows a citation style the app no longer uses.
