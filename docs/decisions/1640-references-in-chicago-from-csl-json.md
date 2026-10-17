# ADR-1640: A harvested entry's reference is drawn in Chicago author-date from the paper's CSL-JSON

- **Status:** accepted
- **Date:** 2026-10-16
- **Pull request:** not yet opened — branch `feat/ask-over-store` (`add-ask-over-store`)

## Context

A harvested entry's reference was "title (year). doi" — no authors, because the store held none
(the author tier was deferred entirely, 2026-10-13). Live answers then cited papers in prose the
model wrote itself, "(Kamasaki et al., 2007, JCB, doi:…)", with authors and a journal no entry
held; the prompt now forbids that (`grounded-answering`), which moves the reference to where the
application draws it. The user asked for authors on every store entry and a reference in a
well-known format, shown in the Reference column.

Options for what the store holds:

1. **A formatted string**, in one chosen style. Simplest to draw; a change of style means filling
   the store again, and the parts cannot be read back out.
2. **The record as CSL-JSON**, formatted when drawn. CSL-JSON is the data format of Zotero,
   Crossref and every CSL processor; the style is a choice made at display.

Options for formatting: a hand-written formatter for one item type, or citeproc-py, a CSL
processor, with the CSL project's own style file.

## Decision

Option 2, the user's choice of CSL-JSON stored and Chicago author-date drawn (2026-10-16). The
store's owner wrote `review_paper.csl_json` for all 66 paper rows from the cached JATS, and the
harvest writes it for new papers (`add-paper-references`, ADR-1750). `store_corpus` reads the column
by name and loads a store without it unchanged; `Paper.csl_json` carries it.

`references.py` — presentation, which no core module may import — formats it with citeproc-py
0.11.1 and `chicago-author-date` (CMOS 18th edition) from citeproc-py-styles 0.1.6, both read on
PyPI 2026-10-16: maintained, and the library's own answer, where a hand-written formatter would be
a second implementation of the style's name and page-range rules.

Two departures from the style, both checked on this store's records:

- **Titles stay as the paper wrote them.** The style title-cases titles, which printed `cdc15` as
  `Cdc15` and `S. pombe` as `S. Pombe` — a gene and a species misnamed. Every `text-case="title"`
  is removed from the style as loaded.
- **A period after a quoted title goes inside the quote**, as Chicago requires; citeproc-py does not
  implement `punctuation-in-quote`.

Where a record cannot be formatted faithfully — none, no author, or a collaboration's name, which
citeproc-py does not support — the entry keeps its plain reference. That is the cheap direction: a
plainer reference still names the right paper. All 48 papers behind the store's 452 values format
(checked 2026-10-16).

**The model is never handed it.** `Entry.reference` stays "title (year). doi", which is what the
tools show; the formatted reference is computed only for the tables and the full entry
(`test_the_model_is_never_handed_the_authors`). Handing a model told to name no paper the names to
write would be asking it to resist them.

Curated entries keep BioNumbers' own reference string. Reformatting them needs their metadata
fetched by PubMed ID, which the user deferred ("maybe later").

## Trade-off accepted

Two new dependencies in the `ask` extra (citeproc-py with lxml, and the styles package's ~2,000
style files) to draw one style. Initials where CMOS 18 prefers full given names, because that is
what the CSL style does. And in a 56px Reference column a full Chicago entry shows only its first
author until a double click opens it.
