# ADR-0240: Stamp every ingest with the identity of the file it read

- **Status:** accepted
- **Date:** 2026-08-28
- **Pull request:** _(not yet opened — branch `feat/corpus-ingestion`)_

## Context

The published export carries **no temporal information whatsoever**. None of its 14 columns is a
date, and every date-shaped string in it belongs to a citation. The file itself has no version, no
release, no changelog.

The consequences of that are worse than they first look. Two corpus files sitting side by side cannot
be told apart or dated; a reader cannot say which of two answers came from the newer data; a defect
found in the corpus cannot be traced to the download it came from; and because ADR-0200 has every
reader fetch the export themselves, two readers on different days may hold genuinely different
corpora while both call the file `bionumbers.jsonl`.

There is no upstream fact to borrow. The only thing that comes close to a fetch time is the source
file's own modification time, and that is a property of the reader's filesystem, not of the data.

## Decision

Every run records what it read.

**A manifest beside the corpus**, named `<corpus>.manifest.json`, recording: the source's full SHA-256
and size in bytes; the source's modification time, **named as such**; the ingest date; the ingester's
version; the row, skip, duplicate and per-flag counts the report states; the `range_fused` count; and
the row limit, if one was applied.

**A short digest on every record.** `source_digest` carries the first 12 characters of the source
SHA-256, so a corpus line separated from its manifest can still be traced to the file it came from.
The consumer's loader models twelve keys and ignores this one.

**The corpus first, then the manifest**, each renamed into place. A corpus with no manifest is a run
that did not finish; a manifest describing a corpus that does not exist would be worse, so the order
is fixed rather than incidental.

**The digest is taken from the bytes the reader parsed**, fed to it from the read loop, so the file is
hashed in the pass that parses it. Hashing separately would mean a second pass over 27 MB and — the
real objection — a second *read*, which could see a different file than the one that produced the
records.

The modification time is called `source_modified` and not `fetched_at`, and the manifest carries a
note saying why. Naming it as a fetch time would assert something the file cannot support.

## Trade-off accepted

**Records are buffered in memory, and the corpus run costs about 69 MB more than it needs to.**
Measured: peak RSS 107 MB against 37 MB at rest. The stamp is a digest of the *whole* file, so it is
not known until the last byte has been read, while the records that must carry it are produced from
the first byte onward. Something had to give. The reader's streaming contract was kept — its memory
stays flat over the 27 MB input, which other callers rely on — and the records are held instead,
bounded by the size of the corpus rather than growing with the input. For an export an order of
magnitude larger this would need revisiting, most likely by writing the corpus unstamped and patching
the fixed-width stamp in a second pass over the output.

**A sampled run's digest describes only the part of the file it read.** `--limit` stops the read, so
the bytes after the limit never reach the hash. The manifest records the limit for exactly that
reason, but a reader comparing a limited run's digest against a full one's will see two different
values for the same file. Recorded rather than fixed: making the digest always cover the whole file
would mean reading past the limit, which defeats the point of the limit.

**The manifest can be separated from its corpus, and then only 12 characters remain.** Twelve is
enough to identify which of a handful of manifests a line belongs to, not enough to be a
cryptographic claim. Putting all 64 characters on 14,294 records would have added roughly 750 KB to
the corpus to defend against a threat nobody has — this is provenance, not tamper-proofing.
