# Validator feasibility probe — 2026-09-09, retrieval arm

The evidence behind
[ADR-0040](../../docs/decisions/0040-what-the-validator-feasibility-probe-established.md).
Twelve subagents (Opus), six corpus entries, two arms each, no code beyond the
quote checker in this directory.

| File | Holds |
|---|---|
| `check_quote.py` | The mechanical verbatim check. The one irreplaceable artifact — every "verified verbatim" claim in ADR-0040 came out of it |
| `PROTOCOL.md` | Both arms' method, what each agent was told, and the corrections adopted for the next runs |
| `GROUND-TRUTH.md` | The six entries and what the source actually says, including the one place the answer key was wrong |
| `RESULTS.md` | Both arms' results, and the independent spot-checks |
| `COVERAGE.md` | The reachability survey — the binding constraint on the whole idea |
| `data/` | Fetched source XML. **Never committed** — see below |

## What may and may not be committed

`data/` is git-ignored via the `data/` rule in the repository `.gitignore`
(line 31), and that was verified with `git check-ignore -v` before anything was
written into it. Confirm it again before adding a file there; the ingester's
guard refuses rather than warns, and an ignore rule only protects the
repositories someone remembered to edit.

**Do not commit:** fetched paper XML, or any bulk corpus-derived listing (the
candidate scan behind `COVERAGE.md` covered 85 entries drawn from a pool of
1,177). Those are corpus derivatives and ADR-0170 keeps the corpus out of every
repository. The bulk listing is *not* reproduced in these files; `COVERAGE.md`
carries only the aggregate counts.

**Committing these files is fine:** the checker, the protocol, the results
tables and the ground-truth notes quote a handful of entries as evidence. That
is citation, not corpus.

## Re-running

Fetch the sources (roughly 100-200 kB each, five files):

```sh
for p in PMC2680341 PMC3159969 PMC5720811 PMC2288635 PMC5005352; do
  curl -sS "https://www.ebi.ac.uk/europepmc/webservices/rest/$p/fullTextXML" -o "data/$p.xml"
done
```

Then check a quote:

```sh
printf 'able to define 20,210 protein-coding genes' | python3 check_quote.py data/PMC2680341.xml
```

## The canary, and why it is not optional

A verification tool must prove it can fail before you believe it passed. A false
all-clear is worse than no check, because it retires the suspicion that would
otherwise have found the problem — and this checker's entire looseness budget is
one 15-entry fold table, which a mangled character silently widens.

Establish all four before trusting a run. Recorded here as they were observed on
2026-09-10, against freshly fetched XML:

| # | Input | Required | Observed |
|---|---|---|---|
| 1 | `able to define 20,210 protein-coding genes` (PMC2680341) | `VERBATIM_OK` | `VERBATIM_OK` |
| 2 | the same with `20,211` | `NOT_VERBATIM` at the digit | `NOT_VERBATIM`, prefix 20/42 — the digit |
| 3 | empty input | `EMPTY_QUOTE` | `EMPTY_QUOTE` |
| 4a | the tag-bearing PMC5005352 sentence, `<sup>` markup intact | `VERBATIM_OK` | `VERBATIM_OK` |
| 4b | the same with `600` changed to `700` | `NOT_VERBATIM` at the digit | `NOT_VERBATIM`, prefix 76/133 — the digit |

Canary 4 is the pair that exercises tag stripping on both sides at once. Extend
the normalisation and it is the one that will break first.

### The fold table is written as escapes on purpose

`FOLD`'s keys are `\uXXXX` escapes and the file is pure ASCII, so it survives a
clipboard, a message and an editor's own normalisation unchanged. This is not
fussiness: these artifacts were reconstructed from a message after the originals
were lost, and the fold table arrived as literal characters. They turned out
intact — all fifteen, verified by code point — but nothing in the file would
have said so if they had not, and a collapsed duplicate key is legal Python that
loosens the check in silence.

Two properties worth asserting after any edit: the table has **15** entries, and
every key is non-ASCII.
