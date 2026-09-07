## Context

See `proposal.md` — Why. Three constraints shape everything below.

**The code exists and works.** `~/Bionumbers-first/src/bionumbers/` holds ~460 lines written against
the real 27 MB file, with ~220 lines of tests, and its README documents the quirks that motivated
each rule. This change is a port, not a design from scratch. The engineering question is not how to
parse the file — that is answered — but how to reshape the port for its new consumer and how to
verify the contract that consumer enforces.

**The consumer is on another branch.** `bionumbers_ask.corpus.load` lives on `feat/ask-agent`;
`src/bionumbers_ask/` does not exist in this worktree, and another session is working on that branch.
So the acceptance criterion — "a JSONL that `bionumbers_ask.corpus.load` accepts" — cannot be
expressed as an import here. This is the one genuinely open design problem, and Decision 3 answers it.

**The corpus is licensed material.** It must not enter the repository, in any branch, ignored or
otherwise (ADR-0170, on `feat/ask-agent`). That rules out committing a corpus, a corpus slice, or a
"small sample" of real entries beyond the tiny hand-built HTML fixture already used for tests.

Also relevant: `pyproject.toml` on this branch is deliberately arranged so that each work package
owns one source tree and one extra, and neither branch edits the other's row. The layout below
follows that arrangement rather than inventing one.

One consequence of the licensing constraint applies to this document: where a cleaning rule exists
because of something observed in the data, the observation is described as a mechanism and a
proportion. No entry text is quoted and no entry identifier is named, since a committed document is
as much a code repository as the code is.

## Goals / Non-Goals

**Goals:**

- A port that keeps every quirk-handling rule the source file forced on the original, with its tests.
- An output whose conformance to the ask agent's loader is *verified*, not asserted, despite the
  loader being absent from this branch.
- A run that is impossible to mistake for a more complete run than it was: no silent truncation, no
  partial file left behind, no dropped row that is not counted.

**Non-Goals:**

- Fetching the export. The reader fetches it; the README says from where and how to cite it.
- Any change to how the ask agent reads a corpus. The contract is an input to this design.
- Re-litigating the cleaning rules. Where the original's behaviour is odd, it is odd because the
  data is; the specs record the behaviour, and changing it is separate work. The one addition is
  descriptive rather than corrective: two flags that say a computed range may be unsound (Decision 9).
  No parsed number changes value in this change.
- Parquet, a database, an index, or a second output format.

## Decisions

### 1. A source tree of its own: `src/bionumbers_ingest/`

`bionumbers` is the grounding validator's package (`bionumbers.cli:main`), and `bionumbers_ask` is
the agent's. A third work package gets a third package, a third extra (`ingest`), and a third
console script row — which is what `pyproject.toml`'s comments already prescribe.

*Alternative: add `bionumbers.ingest` inside the existing package.* Rejected. Both branches would
then edit `src/bionumbers/__init__.py` and the same dependency list, which is precisely what the
one-package-per-work-package arrangement was set up to avoid. It would also couple the ingester's
install to the validator's stack (`anthropic`, `httpx`, `lxml`, `pint`), none of which it needs.

Modules, following the original: `parsing/html_table.py` (source format in), `cleaning.py` (raw row →
record), `model.py` (the record), `validation.py` (the report), `io.py` (corpus out), `cli.py` (the
command). Read as a **pipeline** whose two ends are the only modules that know a file format — the
HTML reader and the JSONL writer. Nothing in the middle knows either.

### 2. JSONL only; `pyarrow` and the parquet output go

The agent reads JSONL. Parquet had one purpose in the original — a canonical columnar form for a
database that was never chosen — and here it would be a 27 MB artefact with no reader, a dependency
to install, and a second serialization path where the contract could drift. Recorded as **ADR-0220**.

*Alternative: keep both, cheaply.* Rejected: "cheaply" is where the drift hides. Two writers means
the JSONL can satisfy the loader while the parquet does not, and nothing would notice.

### 3. Verifying the loader contract in three layers

The loader's failure modes are the interesting part. Reading its code: it raises
`CorpusUnavailable` on the **first** unusable line, aborting the whole corpus; it coerces `""` to
`None` for scalars but `""` is *not* `None`, so an emitted `""` would satisfy its has-a-value branch
and blank out range-only entries; and `tuple()` over a keywords *string* yields one entry per
character, silently. These are the traps to test against, and they are all invisible to a test that
merely checks keys are present.

So:

- **(a) A contract test in this branch.** The required keys and their accepted JSON types are written
  as one literal list in the test, with a comment naming its source (`bionumbers_ask.corpus.Entry`,
  `feat/ask-agent`). It runs a real ingest of the fixture and asserts every emitted line against it,
  trap by trap: absent scalars are `null` and never `""`, `keywords` is an array and never a joined
  string, `entry_id` is a number.
- **(b) A round-trip test that activates on merge.** `pytest.importorskip("bionumbers_ask.corpus")`,
  then ingest the fixture and call the real `load()`. It skips in this branch and becomes a live test
  the moment this lands on `dev` alongside the agent — which is also the moment loader drift would
  otherwise start going unnoticed.
- **(c) A one-off verification during implementation.** Extract the loader into the scratch directory
  with `git show feat/ask-agent:src/bionumbers_ask/corpus.py`, and load a produced corpus with it.
  This touches neither the branch nor the other checkout, and the extracted copy is never committed —
  the same discipline as fault seeding: work in a copy, leave nothing behind. Its result is recorded
  in `tasks.md`.

Recorded as **ADR-0210**.

*Alternative: vendor `corpus.py` into this branch's tests.* Rejected. Two copies of a contract drift,
and the drift is silent in the one direction that matters — the vendored copy keeps passing while the
real loader has moved on.

*Alternative: defer verification to the merge.* Rejected. The work package's done-criterion is that
the loader accepts the output; a port whose acceptance nobody has observed is not finished.

### 4. The output file appears only on success

Write to a temporary file beside the destination and rename it into place after the last row. A
rename within a directory is atomic, so the reader sees the previous corpus or none — never a corpus
that is short by however many rows the run got through. This matters more here than usual: a
truncated corpus loads cleanly, answers questions, and is missing entries nobody can enumerate.

### 5. Every row by default; a limit that announces itself

The original defaulted to `--limit 200`, a first-pass sample. Inverted: the default is the whole
file, `--limit N` samples, and the report states when a limit was applied. A 200-row default here
would hand a reviewer a corpus that looks like the corpus.

### 6. Flag and count; never drop

A row the cleaner cannot fully interpret still becomes a record, with a flag naming what failed; a
row that is not data at all (the trailing padding rows) is counted as skipped. Flags ride on the
emitted record as well as being aggregated in the report, so a downstream reader can tell a recovered
number from a measured one without re-running ingestion. The trade-off is a corpus containing
entries with no scalar value — ~23% of rows, the external-link ones — which the agent must handle;
the alternative is a corpus with 3,000 invisible holes. Recorded as **ADR-0230**.

### 7. `pydantic` stays, and earns it

The record model is the one place where the null-versus-empty-string discipline can be declared
rather than hand-written: `value: float | None` makes an emitted `""` a construction error at the row
that caused it, not a corpus-wide load failure at the reader. `model_dump_json()` is then the whole
writer.

*Alternative: stdlib dataclasses, as `bionumbers_ask` uses.* Rejected — it moves that discipline into
hand-written serialization, which is exactly the trap the loader's own docstring documents. One
dependency, in one extra, to close it.

### 8. The chunked stdlib parser stays

`html.parser` fed 1 MiB at a time, yielding rows as they complete. `lxml` is already a dependency of
the `validator` extra, but the source is one flat `<table>` with no nesting to exploit; adding it to
`ingest` would buy nothing and cost a dependency. Cell content stays as raw inner HTML through
parsing so that cleaning can *detect* injected markup rather than have it dropped before anyone can
flag it.

### 9. Two flags for a fused range, and no change to the bounds

Bounds are the lowest and highest number in the range cell. Where a cell names a second quantity,
one of the two bounds comes from that other quantity, and the result is a range that reads as a
single measurement while spanning two. This is confirmed behaviour, not a hypothesis, and the
population is measured: over a full corpus, 833 of the 6,146 entries carrying a parsed range come from
a cell holding more than two numbers, with 195 of those spanning more than a hundredfold and 50
unjudgeable by ratio because a bound is zero or negative. That is an upper bound on damage — several
measurements of one quantity are a legitimate reason for a wide range — which is exactly why the
decision is to *count* the class rather than guess at a rule for it.

**How the number is counted has been wrong twice, both times upward.** Applying the criterion to the
stored range text rather than to the parse gives 1,716, because an external-link filename's escape
sequences supply extra digits. Removing the URL first gives 1,222 — and that was still wrong, because
the number extractor read `2×10^5` as three numbers and `150,000` as two, so notation counted as fused
quantities. Reading a caret exponent, a `×10^` mantissa and a thousands separator as part of one
number gives 833. The lesson is that a flag over a tokenizer is only as good as the tokenizer: the
heuristic was never the dominant error, the lexer was, and no amount of narrowing the heuristic would
have found that.

So: `range_multi_number` (more than two numbers were read from the cell) and
`range_prose_between_bounds` (text stands between the two numbers that became the bounds). Bounds
are computed unchanged. The first condition is purely mechanical and its population is already
measured; the second is a heuristic and its false-positive rate is unknown, so implementation
includes measuring both over a full corpus before the flags are considered done.

The **predicate is carried as its own field**, `range_fused`, and that field — not the flag names —
is what `add-ask-agent` consumes to stop presenting such a range as a measurement. The first draft
made the two names the contract and let the consumer test `parse_flags` for them; the ask session
refuted it with counts. `parse_flags` is a reporting vocabulary of eight names, five `range_`-prefixed
and only two about fusion: `range_plus_minus` and `range_mean_sd_embedded` mark *successful* parses,
`range_is_link` and `no_scalar` mark rows with no scalar at all. A non-empty test selects 5,148
records on the existing corpus and a prefix test 5,494, against 1,445 — so either rule would mark
thousands of correctly-parsed entries in a user-visible marking and teach the reader to ignore it.
Any name-matching rule also contradicts declaring the names internal: a consumer cannot evaluate
"names a range concern" without the taxonomy. And the vocabulary a consumer can *observe* is not the
one the cleaner can *emit*: the counts above come from what fired in one corpus — six names — while
the cleaner raises eight, `value_unparsed` and `injected_html_removed` simply not having occurred in
that file. A rule derived from the observed six breaks the first time the seventh fires, with nothing
having changed and no version to blame. A contract inferred from a data sample is not a contract. One boolean is read directly, forwarded to the model
without interpretation, and immune to renaming inside `parse_flags`. Recorded with **ADR-0230**.

*Alternative: one flag with both conditions folded in.* Rejected narrowly: a consumer can already
treat either as one signal, and keeping them apart is what lets the report separate a measured
population from a heuristic one.

*Alternative: fix the parse.* Out of scope, and premature — the rule that would separate a fused
range from a legitimately wide one is not known yet, and the flags are what make it knowable.

### 10. Stamp the ingest, because nothing else can

The export contains no temporal information: no column is a date, and the date-shaped strings in it
all belong to citations. Once a download's file time is gone, two corpus files are
indistinguishable and undatable, and no later analysis can recover what was lost. Stamping is nearly
free and strictly one-directional, so it happens now.

A manifest beside the corpus is the authoritative record: source checksum and size, the source file's
modification time (the only available proxy for the fetch — the ingester cannot know when the reader
downloaded the file, and should not pretend to), the ingest date, the ingester version, the run's
counts, and any row limit. Each record additionally carries a 12-character prefix of the source
checksum, because a corpus file gets moved, renamed and split, and a sidecar does not follow it. The
full digest stays in the manifest; the prefix is the join key. Recorded as **ADR-0240**.

*Alternative: a header line in the JSONL.* Rejected, and worth stating because it looks natural: the
consumer's loader requires an identifier on every line and raises on the first line without one, so
a header line would make the corpus unloadable.

*Alternative: manifest only.* Rejected — it is the tidier output and it fails at precisely the moment
it is needed, when the corpus has been separated from the file that described it.

### 11. Cleaning order: unescape before stripping

The ported cleaner strips tags and then unescapes entities. On this export that is backwards in a way
that is invisible from inside the code: the injected markup appears only as `&lt;IMG …&gt;` (20,411
occurrences, zero literal `<IMG`), so the tag pattern matches nothing and the unescape then produces a
live tag that nothing strips again. Two failures follow from the one ordering — the markup reaches the
output, and the flag that is supposed to report it is computed on the pre-unescape text and so reports
zero. The existing corpus carries the tags in `keywords` on 10,206 of 14,294 records with
`injected_html_removed` at zero, which reads as a clean corpus.

The consequence reached retrieval, not just display: the ask agent matches a keyword argument as a
case-insensitive substring, so `img`, `html` and `src` matched 10,206 entries and returned a total that
looked like a fact about biology. Found there, in the entries panel, not here.

The fix is to unescape first, strip second, and repeat until stable; the flag is computed from the
unescaped text, at one boundary every field passes through rather than per field — a per-field fix is
one refactor away from being half-applied.

The lesson generalises twice. First past this field: the test that would have caught it did not exist
because the fixture used the literal form the source never produces. Second past this defect — an
absence inferred from a data sample is not an absence, which is the stronger form of the rule and
applies to any counter, not only to flags. It applies to this fix's own scope: the markup appears only
in `Keywords` in the file we have, and that is one sample. `Range` is the column that would hurt, and
it is where the two defect classes meet — a manufactured tag there puts an escaped filename's digits
within reach of number extraction, raising `range_fused` in a way no reader could distinguish from a
genuine fusion of two quantities. So the injection test covers every column, not the one observed. Requirement in
`specs/measurement-cleaning/spec.md`; the record-boundary assertion and the rule against accepting an
unexplained zero flag count in `specs/ingestion-integrity/spec.md`.

## Risks / Trade-offs

- **The loader drifts on `feat/ask-agent` while this is in flight, and the restated contract goes
  stale silently.** → The contract is one literal in one test, with a comment naming its source, so
  drift is visible where it is read; the round-trip test (3b) becomes live at the merge, which is the
  first moment both halves coexist and therefore the first moment drift could be caught mechanically.
- **The micrometre normalization could go the wrong way.** The agent's own fixture stores Greek mu
  (U+03BC). Normalizing to the micro sign (U+00B5) instead would make every unit comparison miss —
  silently, since both render identically. → An explicit test asserts the Greek mu and asserts the
  micro sign is absent, and the direction is stated in the spec.
- **The full 27 MB run cannot be exercised in CI**, since no corpus may be committed. → Fixture tests
  cover the rules; a one-off full-file run at implementation time records row, skip and flag counts in
  `tasks.md` as a baseline a later run can be compared against.
- **A duplicated identifier reaches the corpus.** The loader accepts it; what the agent's repository
  does with two entries sharing a BNID is out of scope here. → Reported per run, and the report names
  the identifiers, so it is a known quantity rather than a surprise.
- **`data/` in `.gitignore` is broad**, and could later hide something intended for the repository. →
  Test fixtures stay under `tests/fixtures/`, which is not covered by it.
- **`range_prose_between_bounds` is a heuristic and could fire on ordinary cells** — a trailing unit
  word, a parenthetical — turning a useful signal into noise the consumer learns to ignore. → Its
  rate is measured over a full corpus before it is called done, alongside `range_multi_number`, whose
  population is already known; if it fires on a large fraction of ordinary two-number ranges, it is
  narrowed or dropped rather than shipped loud.
- **The manifest's fetch time is a proxy, not a fact.** A source file's modification time can be
  preserved from the server, or reset by a copy, so it can be wrong in either direction. → It is
  recorded as the source file's modification time and named as such, never as "fetched on"; the
  ingest date beside it is exact.
- **A port carries the original's blind spots along with its rules.** Its tests pass, which says
  nothing about what it never tested. → Fault seeding over `cleaning.py` and mutation testing over
  the cleaning and writing modules, per `CLAUDE.md` — a parser and a provenance-carrying writer are
  exactly the code whose silent bugs are unfalsifiable to a reader.

## Migration Plan

Nothing to migrate: new capability, new package, additive `pyproject.toml` rows. This branch lands
after task group 8 of `add-ask-agent`. Rollback is reverting the merge — no consumer depends on the
ingester, and a corpus already produced stays valid, since the output is a file the reader holds
rather than state the project owns.

## Open Questions

- Should the full-file baseline (row, skip and flag counts) be committed as a small text artefact, so
  a later run's report can be diffed against it? Deferrable: it changes no spec, no interface and no
  task beyond adding one file, and the counts have to exist before the question is worth answering.
- Once the agent has run against a full corpus, some parse flags may prove uninformative and others
  worth splitting. Deferrable for the same reason: it needs the corpus to exist first.
- Whether a fused range should eventually be corrected rather than flagged, and by what rule. Not
  deferrable out of laziness: the rule that separates a fused range from a legitimately wide one
  cannot be written before the flagged population can be inspected, which is what this change
  produces. See `proposal.md` — Deferred, for the measured exposure.
