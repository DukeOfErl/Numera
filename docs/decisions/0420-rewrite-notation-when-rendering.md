# ADR-0420: BioNumbers' notation is restated when rendering to the model, never in the corpus

- **Status:** accepted
- **Date:** 2026-09-01
- **Pull request:** _pending — feat/scinumbers-citation-form_

## Context

The model is asked to cite as `[[100002]]` (ADR-0410). The corpus's own entry prose
cites sibling entries as `Range for E. coli B. See BNID 102065, 104333`, and that
prose is handed to the model verbatim in `comments:` and `method:`.

So the model reads one notation and is asked to write another, in the same breath.
That is the likeliest reason for it to answer in a form the parser was not told to
expect, and it is the corpus that puts it there — a systematic cause, not an
occasional slip.

Three places the notation could be fixed:

1. **At ingest.** `cleaning.py` already rewrites this text — it unescapes entities,
   strips the export's injected `<IMG>` markup, normalises two micrometre glyphs.
   One more step would make everything downstream consistent.
2. **At render time**, in the string `tools.py` builds for the model.
3. **Not at all**, tolerating the mixed notation in the parser.

Option 1 was rejected, and the reason is worth recording because it looked like the
tidiest answer. It edits the source's words. This project marks what the source did
not claim and never repairs it (ADR-0190), and flags rather than silently correcting
(ADR-0230); a stored corpus that says `[[102065]]` no longer records what BioNumbers
wrote. It would also foreclose showing raw entries — a planned view whose whole
point is that it is the source's text and not ours.

Option 3 alone was rejected because tolerating a cause is not removing it.

## Decision

`tools.py` restates the source's cross-references in the model's notation **as it
builds the string it hands to the model**, and nowhere else. `bionumbers.rewrite`
does the restating; the corpus, the entries table and every surface a person sees
keep BioNumbers' words.

```
corpus.jsonl           "Range for E. coli B. See BNID 102065, 104333"   ← untouched
entries table (human)  "…See BNID 102065, 104333"                       ← attribution
tools.py → the model   "…See [[102065]], [[104333]]"                    ← our rendering
```

This is a rendering decision, of the same kind `tools.py` already makes throughout
that function: the labels, the `caution:` sentences that state in our words what the
source never said in those words, and the `cites:` line that extracts
cross-references the source wrote inline. Nothing persistent changes.

The `cites:` line is restated too. It previously listed bare numbers — citations in
no notation at all, unusable by a model told to cite in one and unparsable if it
copied them.

**A rendering, never a repair.** What is not an identifier passes through exactly as
written: `BNID 104 678` fails the width floor and is left alone rather than
half-converted into a citation the source never made.

**Display names the source.** Because the two purposes came apart, so did the two
functions: `citations.format_citation` produces the parseable form for the model, and
`bionumbers.label` produces `BNID 100002` for a person. They were one function, and
the machine notation leaked straight into the entries table the moment the model's
form changed — which is how this distinction was found.

## Trade-off accepted

**A third representation of the same text now exists.** Stored, displayed, and
rendered-to-the-model. Anyone reasoning about what the model saw must remember it is
not byte-identical to the entry. The test asserting all three at once
(`test_the_corpus_keeps_the_sources_words_and_the_model_gets_ours`) is what keeps that
from being folklore.

**Restating happens on every retrieval** rather than once at build time. It is a
regex substitution over two short fields, against a model call — not measurable.

**It does not remove the reader's own use of the notation.** A person typing
`BNID 100002` into a question still puts it in the transcript, which is why the
parser tolerates it as well (ADR-0410). This decision removes the cause the corpus
creates, not every cause.
