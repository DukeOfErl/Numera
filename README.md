# BioNumbers

Tools for working with the [BioNumbers](https://bionumbers.hms.harvard.edu/) database of useful
biological quantities — building a corpus from the published export, answering questions against it
with citations, and checking that those answers are grounded in it.

Three work packages live here, each in its own package and each installed by its own extra:

| Package | Extra | What it does |
|---|---|---|
| `bionumbers_ingest` | `ingest` | turns the published export into a JSONL corpus, with provenance |
| `bionumbers_ask` | `ask` | answers natural-language questions using only entries it retrieved |
| `bionumbers` | `validator` | checks that an answer is grounded in the corpus |

This branch carries the ingester. The other two arrive on their own branches.

## The corpus is never committed, and that shapes everything

The published BioNumbers data has unresolved licensing, so **nothing derived from it may enter this
repository** — not the 27 MB export, not a corpus built from it, not a sample.

That is why this repository ships an *ingester* rather than a corpus: you fetch the export yourself
and build the corpus locally, so nothing is redistributed ([ADR-0200](docs/decisions/0200-ship-an-ingester-not-a-prepared-corpus.md)).
The cost is real and falls on you — the agent does not run until you have done the fetch.

Two guards back this up rather than relying on memory. `data/` is git-ignored, and **the command
refuses to run at all if git would track its output**, naming the repository and exiting non-zero. If
you run it from the wrong checkout it stops instead of quietly writing unlicensed data onto a
committable path.

## Getting the export

Fetch it from BioNumbers yourself, as published: a single HTML `<table>` served with an `.xls`
extension, around 27 MB: 14,297 rows over 14 columns, of which 14,294 are data and three are
trailing padding. Do not convert, rename or pre-process it —
the ingester reads it exactly as published, and its quirks are the reason this code exists.

**Cite BioNumbers if you publish anything derived from it.** The database asks to be cited as
Milo R, Jorgensen P, Moran U, Weber G, Springer M, *"BioNumbers — the database of key numbers in
molecular and cell biology"*, Nucl. Acids Res. 2010, and individual entries carry their own primary
references, which the corpus preserves per record.

## Building a corpus

```bash
uv sync --extra ingest
uv run bionumbers-ingest path/to/BioNumbers.xls
```

That writes `data/processed/bionumbers.jsonl` (git-ignored) plus a manifest beside it, and prints a
report. Use `-o` for another path, and `--limit N` to process only the first N rows — **not** the
default, because a sampled corpus looks complete and is not.

## What you get

**The corpus** — one JSON object per line, one line per data row. Twelve keys are a contract with the
ask agent's loader; the rest are extra and it ignores them. Absent numbers are `null` and never `""`,
and `keywords` is always an array.

**The manifest**, `<corpus>.manifest.json`. The export carries no date and no version anywhere, so
without this two corpus files cannot be told apart or dated. It records the source's checksum, size
and modification time, when the run happened, which version ran, and every count from the report. The
corpus is written first and the manifest second, so a corpus with no manifest is a run that did not
finish ([ADR-0240](docs/decisions/0240-stamp-every-ingest.md)).

Every record also carries `source_digest`, twelve characters of that checksum, so a line separated
from its manifest can still be traced to the file it came from.

**A report** of what the run could not interpret, with a count per flag — zeroes included, because a
flag reporting zero is a claim about the world and needs an argument from the code before anyone
believes it.

The same export always produces a byte-identical corpus, so two people can compare their builds and
learn something from a difference.

## What the flags mean

Nothing is dropped and nothing is silently corrected. A cell the ingester cannot read cleanly still
becomes a record, with a flag naming what went wrong ([ADR-0230](docs/decisions/0230-flag-and-count-never-correct.md)).

`parse_flags` is the ingester's own vocabulary and its names may change. **Two boolean fields are the
stable contract, and a consumer should read those rather than match on flag names:**

- **`range_fused`** — the stored bounds may come from two different quantities. Bounds are the lowest
  and highest number in the cell, so a cell naming a second measurement contributes a bound to the
  first, and the result reads as one measurement while spanning two. 1,418 records.
- **`range_qualified`** — the source did not state a closed interval. `<0.001` becomes the interval
  from 0.001 to 0.001, which asserts an exact equality where the source said *less than*; `~5`
  likewise loses its hedge. 2,233 records.

A record can carry either without the other, and they need different words in a caveat. Neither means
the range is *implausible* — judging that needs the comment text, and the ingester does not judge.

## Development

```bash
uv run pytest                 # offline by default
uv run pytest -m network      # the tests that hit a real service
uv run ruff check . && uv run ruff format --check .
```

Behavioural requirements live in `openspec/`, decisions in `docs/decisions/`, and diagrams in
`docs/diagrams/`. `CLAUDE.md` describes how the code is organised and the testing practices this
project holds itself to.
