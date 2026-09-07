# ADR-0170: The corpus stays outside every repository

- **Status:** accepted
- **Date:** 2026-08-26
- **Pull request:** _pending — `feat/ask-agent`_

## Context

The corpus is derived from BioNumbers, a public database of quantitative biology.
Its licensing for redistribution is unresolved. Three checkouts under
`~/AI Engineering/` share one origin, so a file committed in any of them
publishes from all three, and git history is permanent — a later deletion does not
undo a push, a clone, a cache or an index.

The pull the other way is real: an agent whose corpus is not in the repository
cannot be cloned and run, which is friction for every reviewer and every future
contributor.

## Decision

The corpus is **an external input supplied at run time** — `--corpus`, or
`SCINUMBERS_CORPUS` — and the loader fails with an explanatory message when
none is given. It is never committed.

> _Amended 2026-08-31 (ADR-0400): the variable was `BIONUMBERS_ASK_CORPUS` when
> this was written. The old name is now refused rather than ignored._

`.gitignore` is anchored and matches the data file as well as the directory
(`/corpus/`, `bionumbers*.jsonl`, `*.corpus.jsonl`), because the corpus is a
single JSONL file and a directory pattern alone would not stop `git add -A`.

Three consequences follow, and each is a decision in its own right:

- **A six-entry sample is committed** at `tests/fixtures/corpus_sample.jsonl`, so
  the whole test suite runs with no corpus and no API key. Six entries is
  de minimis; it is not a licence to commit a larger slice.
- **The structured trail carries no entry text** — search terms, identifiers and
  token counts only — so a log file can be shared without the corpus's licensing
  travelling with it.
- **The record of corpus entries that are clearly wrong** is kept as a file beside
  the corpus, outside every repository, for the same reason.

## Trade-off accepted

The project cannot be cloned and run. Anyone who wants to use it must obtain a
corpus separately, and — because what BioNumbers distributes is a 27 MB HTML
table carrying an `.xls` extension rather than the JSONL this agent reads — must
also convert it, which is currently done by a separate ingestion project.

That friction is accepted knowingly, and it is why the README states the
provenance and the reason plainly rather than quietly omitting the source.
Reducing it by bringing the ingestion into this repository is a candidate work
package; reducing it by committing the data is not.
