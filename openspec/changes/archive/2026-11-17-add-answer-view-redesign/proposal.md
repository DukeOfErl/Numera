## Why

The demo on 2026-10-19 shows the ask agent answering from the harvest store, and the page was not
designed for what the store adds: stars, a simulated mark, objections, long property names, full
references. Yoav worked out a redesign on a Claude Design canvas ("SciNumbers Ask redesign",
https://claude.ai/artifact/4H8KtYtaJaMns2kWyzpcAh). Its main moves:

- **Citations become pills.** Each cited number gets one small pill with an entry number, the
  stars, `sim` and ⚠. Long identifiers leave the prose. `#` is dropped because it collides with a
  paper's own "#1–#4" ring labels.
- **The table and the side panel merge into one evidence column.** It holds an evidence list, with
  the full entry opened in place, objection text included.
- **The page's chrome quiets down.** The sidebar is collapsed, the prototype warning becomes a line
  in the header, and the retrieval box becomes one line under the answer.

The canvas's sample content (objection text, conditions) is illustrative; what is drawn here is read
from the store.

## What Changes

- **Numbered pills** replace the grey superscripts on the web.
  - Entries are numbered through the session, so a pill in an older answer still names one entry.
  - A pill carries the entry's number, its stars, `sim` where the review was simulated, and ⚠ where
    someone objected. The identifier shows on hover and in the evidence list.
  - The stored answer, the trail, the evaluation and the terminal keep `[[id]]`.
- **The evidence list** is an HTML table, so long property names wrap. Its columns are #, Entry,
  Value, Trust and ID.
  - Entry holds the property, with the organism and "first author year" in grey under it.
  - Value holds the value with its units, with any caveat marks after it.
  - The caveat-mark column, the Units column and the Reference column go.
  - A legend under the list explains only the marks shown.
  - Uncited entries sit under one collapsed row.
- **Opening an entry.** The entry numbers under the list open the full record in place: pills for up
  to twelve entries, a dropdown above that. The record holds the full reference with its links, the
  value, any objection (who objected and what they said), the method, the quote, the conditions,
  what is not stated and the domain. The Trust cell no longer carries objection text.
- **Simulated mark.** `sim` replaces `#` everywhere a tier is drawn, the terminal included.
- **The sidebar is collapsed by default.** It holds the account, the budget, the data credit and,
  for roles granted it, the trail. The entries leave it.
- **Header and footer.** The header has the title, a subtitle naming the data, and an amber
  prototype line. Under the question box are the records note and who is signed in.
- **Search line.** The retrieval box, once finished, is labelled with what was searched and how
  many entries were retrieved and cited.
- **First view.** A heading, a short paragraph and example questions that ask themselves, with the
  evidence column empty and saying what will appear there.

## Capabilities

### Modified Capabilities
- `grounded-answering`: how the entries accompany an answer, how a cited entry's tier is drawn,
  and where caveat marks sit. Adds numbering through the session and opening an entry in place.
- `store-corpus`: where a harvested entry's Chicago reference is shown.
- `user-identity`: the sidebar holds the trail without a tab strip, because the entries left it.

## Impact

- `src/scinumbers_ask/web.py`, `streamlit_app.py`, `trust_marks.py` and `references.py`
  (short author-year).
- `entries_table.py`, for the row's short reference only.
- Many web-driver tests change, because they assert the superscripts, the dataframe and the
  sidebar's entries.
- The terminal's layout is unchanged apart from `sim`.
- The sign-in door's demo keeps its superscripts (ADR-1240) until a later change.
