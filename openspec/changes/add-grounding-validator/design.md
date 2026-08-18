## Context

See `proposal.md` — Why. This repository is an empty `uv`-managed Python scaffold, so every decision
here is greenfield. The requirements this design implements are in `specs/source-retrieval/`,
`specs/evidence-grounding/`, and `specs/grounding-benchmark/`.

Three constraints shape the approach:

- The benchmark corpus cannot live in this repository (licensing is unresolved), so it must be an
  external input with a documented minimal shape.
- Source access is restricted to openly licensed full text, which rules out a PDF-acquisition stack
  for this change.
- The validator must be auditable: every verdict has to carry evidence and say how it was reached.

## Goals / Non-Goals

**Goals:**

- Decide verdicts using the cheapest mechanism that is sufficient, and make it visible which
  mechanism decided each one.
- Keep the corpus, the source provider, and the adjudicating model individually replaceable.
- Produce per-entry records rich enough to debug a wrong verdict without re-running the pipeline.

**Non-Goals:**

- Throughput and parallelism engineering. Correctness and measurability first; the subset is ~258
  entries, which does not justify a job queue.
- A storage layer. Results are files, not a database — the database choice is deferred until the
  extraction pipeline exists and its access patterns are known.
- Any persistence of retrieved full text beyond a local cache keyed by identifier.

## Decisions

### Corpus is an external file conforming to a documented minimal shape

The benchmark reads a JSONL file supplied at run time and requires only the fields it uses: a stable
identifier, property, organism, value or range, units, source identifier, and the curator quotation
fields. Producing that file is out of scope.

*Alternatives considered.* Porting or vendoring the ingester from the `~/Bionumbers-first` prototype
would duplicate working code, tie the benchmark to one dataset's column names, and put us a step
closer to committing the corpus — directly against the swappable-input requirement. Re-ingesting
from the raw export inside this change would do the same and add HTML-parsing quirks to this work
package's surface area. Reading a prepared file keeps the coupling to a documented schema rather
than to a particular producer, and the prototype's existing output already conforms.

### Two stages, cheapest-first, with the mechanism recorded

Stage one extracts every numeric mention from the document with its structural location, normalises
units on both sides, and compares with a tolerance. Stage two asks a language model, per surviving
candidate, whether the mention describes the claimed quantity.

The point is not only cost. The two stages fail in different ways and are measured separately:
stage one's failures are recall failures against gold spans, stage two's are precision failures on
candidates. A monolithic "read the paper and decide" prompt produces one number and no handle on
which half is wrong — and it would put a model call on the critical path of every entry, including
the many where a single unambiguous mention makes the answer mechanical.

*Alternative considered.* Retrieval-augmented selection (embed the claim, retrieve similar passages)
was rejected for this stage: the claim is a number with units, and lexical-numeric matching after
unit normalisation is both more precise and cheaper than semantic similarity for that.

### Europe PMC as the single source provider

One API covers open-access full text and indexed bioRxiv/medRxiv preprints, and serves JATS XML
directly — so preprint substitution and version-of-record retrieval share a code path and a parser,
and no PDF text extraction is needed. The provider is confined behind the `source-retrieval`
interface so it can be swapped or supplemented (Unpaywall, PMC OAI) without touching grounding.

Retrieval is cached on disk keyed by document identifier and version. The benchmark is re-run often
during development; re-fetching the same few hundred documents each time is both slow and impolite
to a free service.

### JATS parsing preserves a structural path per span

Documents are parsed into a tree of sections, paragraphs, tables, and captions. Every extracted
span carries a structural path (section → paragraph index, or table → row/column) plus character
offsets within its block. This is what makes evidence citable, what the benchmark compares against
curator location pointers, and — later — what a human reviewer clicks.

Figure content is marked as not machine-readable rather than omitted, so a claim whose value lives
only in an image is reported `UNVERIFIABLE` instead of `NOT_FOUND`.

### Units via Pint; numeric parsing is hand-rolled

Pint handles dimensional analysis and conversion, which is the part that is genuinely hard to get
right. Detecting numeric mentions in prose is not something Pint does, and it has to be purpose-built.

A prior ingestion prototype catalogued the notation variants empirically, and that catalogue is
reproduced here rather than referenced, because it is the parser's specification and its test
corpus. These variants are **not artifacts of one dataset's export format** — they are how
quantities are written in the scientific literature, so the same parser faces them twice: once in
the corpus, and again in every paper it reads.

| Variant | Forms seen |
|---|---|
| Micro sign | `μm` (U+03BC, Greek small mu) and `µm` (U+00B5, micro sign) — visually identical, different code points |
| Range separator | hyphen (`0.44-1.79`), en or em dash (`1–2`), the word `to` (`1.94 to 2.72`) |
| Uncertainty | `±`, `+-`, `+/-`, read as `value ± Δ` → `[value − Δ, value + Δ]` |
| Sign | leading `-`, and the Unicode minus `−` (U+2212) |
| Scientific notation | exponent-letter (`1.5e-3`) and times-power-of-ten forms |

The last two interact in the one case worth calling out as a defect class: **a negative exponent
must never be read as a range separator.** `1.5e-3` is one value, not a range from `1.5e` to `3`.
A naive split-on-hyphen range parser gets this wrong silently, producing a plausible-looking
interval, and it will do so on real papers as readily as on the corpus.

Distinct from the above, the prototype also catalogued quirks belonging to its **source export**
specifically — a leading apostrophe left by Excel, injected `<IMG SRC=…>` markup, and rows whose
value is only a link to an external table. Those belong to whatever produces the corpus file and are
deliberately out of scope here; only the notation variants above are this change's concern.

Default comparison tolerance is 2% relative, configurable and reported with every verdict. That
figure comes from the exploration pass over the cytoskeleton slice, where it recovered 87% of
curator quotations containing the claimed value; it is a starting point to tune against the
benchmark, not a derived constant.

### Adjudication model

Models are reached through **OpenRouter**, matching the account that is actually available and the
approach used elsewhere in this work. **Claude Opus 5 is not available on that account** — an earlier
draft of this section named it, which would not have run.

Development uses an inexpensive model; **Claude Opus 4.7** is the most capable option available and is
the target once the pipeline is proved. The model is configuration, so the same benchmark subset can
be scored on both and compared. The model identity and whether a model was consulted at all are
recorded per verdict, as the spec requires — which is also what keeps a weak model's failures
distinguishable from a defect in the pipeline.

*To verify before implementing group 5.* Two things follow from going through OpenRouter rather than
a provider SDK directly. Structured output support varies by model there, and a model without native
support returns prose that must be parsed — so either a model with native support is chosen, or the
adjudicator tolerates parsing. And OpenRouter reports the cost of each request in its responses,
which is a better source for any spend accounting here than a local price table.

**Open question for the user:** whether a direct Anthropic API key exists for this project. If it
does, the provider SDK remains an option and this decision is worth revisiting; if not, OpenRouter is
the only route and the notes above apply.

The adjudication prompt sees only the candidate span and its surrounding block, not the whole
document — which keeps each call small and independently reviewable. Because most entries are
expected to resolve deterministically, model spend should scale with ambiguity rather than with
corpus size.

## Risks / Trade-offs

- **Open-access coverage may be low.** ~20% of corpus entries carry no source identifier at all, and
  an unknown further fraction cite books or paywalled work with no preprint. → Coverage is a
  reported headline number, not a hidden failure; if it comes in low, that is a finding about access
  strategy rather than a defect in the validator.
- **Gold spans come from curator quotations, which are themselves human transcriptions.** A
  quotation may paraphrase or contain a typo. → Measured as a distinct stratum: entries whose
  quotation does not contain the claimed value are marked as lacking gold evidence rather than
  counted as failures.
- **The adjudicator is a language model judging a task we are also using a model to build.** →
  Verdicts carry evidence spans that a human can check directly, and the benchmark reports
  evidence agreement separately from verdict agreement, so a model that returns the right verdict
  for the wrong reason is visible.
- **Tolerance is a single global knob.** A 2% relative tolerance is generous for a precisely
  measured constant and tight for an order-of-magnitude estimate. → Reported with every verdict so
  its effect is auditable; per-property tolerance is deferred until the benchmark shows it matters.
- **Europe PMC is a single point of dependency.** → Confined behind the retrieval interface; the
  disk cache means an outage degrades development rather than blocking it.

### Preprint version selection

Where several preprint versions of a work exist, retrieval takes the one published **closest in
date to the version of record**, falling back to the newest when no date is known. The curator read
the published paper; the preprint nearest that date is the closest available proxy for what they
saw, which is what the benchmark is scoring against.

**To be revisited** when the project moves from benchmarking against curated entries to searching
for new content to add to the database. At that point there is no curator and no citation date, and
the newest version is likely the right default — the reason for this choice disappears with the use
case that motivated it.

*Implementation note.* Europe PMC exposes preprint versions as separate `PPR` records with distinct
publication dates rather than as a version field; `versionNumber` is absent from core results. The
recorded version label therefore carries publisher, date, and `PPR` id.

## Open Questions

- Which structural-path serialisation to use for evidence locations. It affects only the record
  format and can be settled during implementation.
