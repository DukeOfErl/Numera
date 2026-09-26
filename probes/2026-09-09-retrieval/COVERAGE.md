# Coverage — the binding constraint

Retrieval works. Whether enough sources are *reachable* is the question that
decides the validator's scope, and it is the one that could still make it
infeasible at useful scale.

## The funnel

| Stage | Count |
|---|---|
| Corpus entries | 14,294 |
| ...with a `reference_pubmed_id` | 11,011 |
| ...and a value or range | 8,696 |
| **Favourable pool** | **1,177** |
| Sampled from it | 150 |
| ...distinct PMIDs resolved in Europe PMC | 126 |
| ...with a PMCID | 72 |
| ...`isOpenAccess=Y` | 28 |
| ...`hasPDF=Y` | 71 |

The favourable pool is: a value or range present, **and** a verbatim quote in
`measurement_method`, **and** a page/table/figure locator, **and** reference
year >= 2005. It is the best-case slice, not a representative one.

`fullTextXML` was then probed on all 72 PMCID papers: **28 returned real XML
(>5 kB), 44 returned empty.**

## `isOpenAccess` is an exact pre-filter

It predicted XML availability **perfectly** — 28/28 yes, 0/44 no. Use it to
filter before attempting retrieval; it costs one lite query.

```
search?query=EXT_ID:<pmid>&resultType=lite&format=json
```

An entry whose source is unreachable is **out of scope**, never
**unconfirmed**. Those are different facts about an entry and must not share a
verdict.

## So: ~22% of the favourable slice

28 of 126. On the whole corpus the reachable fraction is **lower**, since the
pool was selected for the properties that correlate with a good source.

## Where the rest hides — structurally, not randomly

This matters: the missing material is not a random 78% that a bigger sample
would dilute.

- **Supplementary files.** For BNID 108345 and 108346, *every* quantitative
  table is Supplementary S1-S8 and absent from the XML. The paper's own prose
  carries the derivation inputs but not the values.
- **Figure images.** The per-depth values for BNID 115327 and the spread for
  109252 exist only as plotted points.

Both are addressable, and both are a larger project than this probe. That is
next probe #1.

## Two dead ends

- **Preprints.** Only 8 entries in the entire corpus cite one, and they are
  oddities (supplemental Excel links; one marked "to be approved once article
  is peer-reviewd"). Not a route to coverage.
- **String-level pre-classification** of whether a target number appears in its
  source: attempted and discarded as unreliable. False negatives on `19,042`
  (comma) and `46.4298 kDa` (unit form), plus coincidental matches. The agent
  is the measurement.

## Note on what is not in this directory

The candidate scan covered 85 entries drawn from the 1,177-entry pool. That
listing is a corpus derivative and is **not** reproduced here — only the
aggregate counts above. See `README.md`.
