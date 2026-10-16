# ADR-1630: The application draws an entry's trust tier; the model never writes it

- **Status:** accepted
- **Date:** 2026-10-16
- **Pull request:** not yet opened — branch `feat/ask-over-store` (`add-ask-over-store`)

## Context

Over the harvest store, every entry has a trust tier read by ADR-0990's rule: curated, or the
highest reviewer role that approved it, with a separate flag where anyone objected and another
where the tier was set by a simulated review (ADR-0960). A reader needs to see it beside each
citation and in the entries table.

Options for who puts it there:

1. **The model writes it**, told each entry's tier and asked to write stars after each citation.
   One more instruction among many; a model that miscounts, forgets, or copies a tier to the wrong
   citation produces a wrong rating that looks exactly like a right one.
2. **The application draws it**, from the store, beside every citation and row it already draws.
   The model is told the tier in words, so it can weigh it, and is asked not to write ratings.

## Decision

Option 2. The model sees `trust: 3 of 5 (scientist, simulated review); disputed`
(`tools.trust_text`) and never a star; `trust_marks` — presentation, which no core module may
import (`test_driver_independence.py`) — draws the stars. The prompt asks the model never to state
a rating in any form — the first live answers wrote "(trust 3/5)" beside stars that already said
it; where it does anyway, its stars are left as text it wrote and the drawn ones still follow
the citation, read from the store. The stored and recorded answer is never altered: only drawing
adds the stars.

**The scale** (user's choice of stars only, 2026-10-13):

| Tier | Drawn |
|---|---|
| curated | ★★★★★ |
| senior scientist | ★★★★☆ |
| scientist | ★★★☆☆ |
| student | ★★☆☆☆ |
| AI reviewer | ★☆☆☆☆ |
| no reviewer approved it | ☆☆☆☆☆ |
| no tier (corpus file) | nothing |

`#` before the stars marks a tier set by a simulated review; `⚠` after them marks a dispute. Both
qualify the tier, so they travel with the stars rather than in the caveat column. `†` was the first
choice for the simulated mark and is taken (no measurement method recorded); `$` was dropped
because Streamlit reads it as mathematics and a reader could take it for a price; `#` was the
user's choice, placed before the stars on their instruction. Its legend line begins with `#` and is
escaped on the web so markdown does not draw it as a heading. A legend states the scale and each
mark once per answer, with its entries table; the first version repeated it under the answer's
prose, and the user had it removed there (2026-10-16).

**Where they are drawn.** On the web, after the grey citation superscript ADR-1240 introduced, at
the prose's own size: <sup>PMC2652108-1</sup> #★★★☆☆⚠. The first version put the stars inside the
superscript; the user's verdict on seeing it (2026-10-16) was that the stars, `#` and `⚠` are read,
not footnoted, so each identifier of a run now gets its own superscript followed by its stars, and
a run with no tiers is drawn as one superscript, as before. The superscript's pattern is now built
from `citations.DELIMITED` rather than a second pattern — it read digits only, and a label would have
been drawn as raw brackets. In the terminal, after each `[[id]]`. In both entries tables, a Trust
column after Units and before the ID, drawn only where some entry has a tier.

**The caveat column.** In the same change, and at the user's request, the table's caveat marks
(`† ‡ § ° ≈ ¡`, and the store's `?` and `∴`) moved from a prefix on the property to a narrow first
column with an empty header (`grounded-answering`). On the web the new columns are paid for by
Organism, ID and Reference, which got narrower so the table still fits the evidence column on the
target browser (`test_the_evidence_column_can_hold_its_table`).

## Trade-off accepted

The model's prose cannot say "this five-star entry" in the reader's own visual terms, only in
words; and an answer read outside the application — a copied paragraph, the trail — carries no
stars. Accepted because the tier is a fact about the store, and the store, not the model, is where
a reader's trust in it should come from. The narrower Organism, ID and Reference columns truncate
more often; a double click opens a cell in full, and the superscript carries the whole identifier.
